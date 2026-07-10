# PROGRESO 19 — activación BookRecorder para revalidación order flow (2026-07-10)

## Dónde está el proyecto (mapa completo)

| Fase | Estado |
|---|---|
| F1 Captura estructural | **CERRADA**: banco 2022→2026, 729 sesiones, 1,014 eventos, 194 features (`_v4`) |
| F2 ADN estructural | **RESPONDIDA**: no predecible con footprint 1-min (AUC 0.43-0.50, PROGRESO_17) |
| F2b A/B order flow (267 eventos con libro viejo) | **POSITIVO PARCIAL** (PROGRESO_18): 40/40 PF 1.22→1.63; ~80% del valor en `profundidad_liquidez`; inconsistente en 80/80; n corto → decisión: NO comprar Databento aún |
| F2c REVALIDACIÓN (spec completo del usuario) | **EN CURSO** — recaptura con BookRecorder para subir n de 267 a ~600+ |
| F3 Simulación Lucid 150k (reglas confirmadas: $9k target / $2.7k daily soft / $4.5k EOD / máx 3 minis) | espera a que F2c dé un filtro estable |

## Prueba actual de grabación (fecha sanity 2024-03-11, 3 corridas)

| Intento | Resultado |
|---|---|
| 1 (recorder no agregado) | nada escrito |
| 2 (usuario dijo listo, no estaba en el chart del replay) | nada escrito |
| 3 (recorder agregado al chart) | **tape ✓** fresco: 39,576 filas, 09:29→09:40, 1,063 KB. **MBP ✗** (sin archivo, sin `bookrec_status`) |

Diagnóstico: `OnNewTrade` dispara (tape ✓) pero `MarketDepthChanged` no → el Market Replay
tiene DESACTIVADA la reproducción de profundidad. Los mbp históricos (2023-2025) se grabaron
en sesiones donde ese checkbox estaba activo.

**ACCIÓN PENDIENTE DEL USUARIO**: en la ventana de Market Replay de ATAS, activar la casilla
de **Market Depth / DOM** al configurar el replay. Sin MBP no se puede grabar el grupo
`profundidad_liquidez` — exactamente el que aportó el 80% del valor en PROGRESO_18.

Nota: el tape termina ~09:40:23 porque el runner detiene el replay al completarse el export
LVN (marker 09:40). Alcanza para las ventanas de flujo del spec (post-touch máx +30s sobre
retests que terminan 09:39:59) — al límite. Si se quisiera colchón, subir `ResearchEndNy`
del indicador; NO necesario por ahora.

## RESUELTO: MBP grabando tras activar DOM en el Replay (2026-07-10)

Sanity 2024-08-06 (día con 12 eventos en el banco): reporte reprodujo EXACTO los 3 LVNs /
12 eventos (replay determinista ✓) y escribió `mbp` 4.8 MB + `tape` 719 KB frescos. La falla
de MBP era el checkbox Market Depth/DOM del Replay desactivado; 2024-03-11 con 0 LVNs era
sesión sin perfil calificante, no falla del recorder.

## OBJETIVO DE LA RECAPTURA (registrado a pedido del usuario)

Grabar libro (MBP) + cinta (tape) de las fechas que no los tienen, para repetir el A/B de
order flow con muestra 2-3× mayor. Cadena: PROGRESO_18 mostró flujo útil en 40/40
(PF 1.22→1.63, 80% del valor en profundidad_liquidez) pero n=267 insuficiente e
inconsistente en 80/80 → 2022 (0 grabaciones) y 2024 (9) son el n gratis más grande →
con n≈600+ y era-split se decide la compra de Databento 5 años. Los eventos LVN no cambian
(replay determinista); lo único nuevo es el libro+cinta.

## Corrida v2 REANUDABLE (la v1 se trabó y fue detenida)

La v1 usaba --force por rango: un cuelgue obligaba a repetir todo. La v2 construye la lista
de fechas PENDIENTES (sin `mbp_*` con mtime de esta campaña, corte 2026-07-10 07:00) y lanza
solo esas con `--dates --force`: 313 pendientes de 315 (2 ya grabadas). Cualquier
relanzamiento regenera la lista y continúa donde quedó. Vigilancia horaria verifica que los
mbp sigan escribiéndose (si DOM se desactiva → Telegram inmediato).

## Al terminar la recaptura (automático)

1. Lanzar recaptura **2022 completo (150 fechas) + 2024 completo (165)** con `--force`,
   ~11-12h encadenadas, vigilancia + Telegram por fecha. (2023 le faltan 138 y 2025 109 —
   ampliables después si el usuario quiere n≈900.)
2. Mientras corre, construir las piezas nuevas del spec (`targets_revalidacion_orderflow`):
   - Parte 1: auditoría de calidad por fecha (cobertura, gaps, duplicados, símbolo, estado).
   - Parte 3: auditoría por evento + `events_excluded_audit.csv` + `ab_dataset_integrity.csv`
     con hashes + event_id con dirección.
   - Parte 4: separación física de resultados vs features + `feature_cutoff_audit.csv`.
   - Ventanas de flujo del spec: pre[-10,-1) / touch[-1,+3) / post[+3,+10) / ext[+10,+30)
     configurables, verificación por evento de que terminan ≤ confirmación (anti-leak).
3. Repetir el A/B idéntico (mismos brackets, cero optimización) con n ampliado + era-split.
4. Informe de decisión final: comprar Databento SÍ/NO con confianza y tabla por grupo.

## Reglas vigentes que gobiernan todo

- Excels jamás se borran por script; X1/X10 intocable; AMBIGUOUS jamás se adivina.
- Features de flujo cortadas en la confirmación (leak PROGRESO_16).
- Ninguna exclusión silenciosa; todo a archivos de auditoría.
- El proceso puede decir NO: si el valor de profundidad no se sostiene con n grande,
  no se compra nada y LVN queda refutado con flujo incluido.
