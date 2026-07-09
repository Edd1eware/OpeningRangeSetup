# PROGRESO 12 — loop multi-temporada, gates y primera temporada DST 2026 (2026-07-09)

## Loop de investigación congelado (definido por el usuario 2026-07-08)

**Gates** (antes de mirar resultados): WR ≥ 50% | PF ≥ 2.0 | RR 1:1 | trades/mes ≥ 4.

**Loop**: correr temporada DST 2026 → si algún segmento pasa gates, lanzar DST 2025 → seguir
retrocediendo temporada por temporada hasta ~mediados de 2022 (frontera de datos de replay de
ATAS). Solo temporadas DST por ahora; EST se agrega después. Detección de frontera: el runner
aborta tras N fallas consecutivas (`--stop-after-consecutive-failures`, default 6) y registra
`first/last_successful_date` + `data_boundary_reached` en el manifest.

**Objetivo final**: pasar cuenta $150,000 de lucidtrading.com respetando sus reglas
(MaxDD $4,500 según estado previo del proyecto OR), farmear payouts. Método: look-ahead en
replay para sacar el ADN de los mejores trades / más frecuentes → pasar la cuenta en el menor
tiempo posible sin que el riesgo la queme.

**Reglas operativas nuevas**:
- Los scripts Python NUNCA borran/sobrescriben Excels generados: `export_results` ahora agrega
  sufijo `_runYYYYMMDD_HHMMSS` si el destino existe. Borrar es SIEMPRE decisión manual.
- Telegram integrado al runner: mensaje de inicio, progreso cada N fechas
  (`--telegram-progress-every`, default 10) con fechas recorridas, OK/FAIL/SKIP, filas
  capturadas, % y ETA; mensaje final con sesiones/LVNs/eventos y WR por bracket; aviso especial
  si se alcanza frontera de datos.

## Resultado temporada DST 2026 (2026-03-09 → 2026-07-08)

Captura: **71/84 OK**, 13 FAIL (2026-06-12 → 06-30). Los FAIL no son frontera de datos: la
ventana Replay de ATAS se atoró en la fecha 11/06 y luego desapareció/perdió visibilidad
("ATAS no aceptó el rango", "Abre y deja visible la ventana Replay"). Esa corrida usaba el
runner viejo sin stop-por-fallas; el nuevo habría abortado tras 6. Reintento de las 13 fechas
lanzado con el runner nuevo.

Reporte (71 sesiones): **62 LVNs, 127 eventos de retest**.

### Gates sobre lo capturado (crudo, sin filtros): NADA PASA — esperado por doctrina

| Segmento | Bracket | Trades | Tr/mes | WR% | PF | EV neto (t, com. 1t) | Falla |
|---|---|---:|---:|---:|---:|---:|---|
| GLOBAL | 20/20 | 36 | 7.2 | 47.2 | 0.89 | -2.1 | WR, PF |
| GLOBAL | 40/40 | 75 | 15.0 | 44.0 | 0.79 | -5.8 | WR, PF |
| GLOBAL | 60/60 | 94 | 18.8 | 45.7 | 0.84 | -6.1 | WR, PF |
| GLOBAL | 80/80 | 105 | 21.0 | 53.3 | 1.14 | +4.3 | PF |
| ACCEPTANCE | 80/80 | 50 | 10.0 | **56.0** | **1.27** | **+8.6** | PF |
| REJECTION | 80/80 | 55 | 11.0 | 50.9 | 1.04 | +0.5 | PF |

Lecturas (n chico, un solo año — NO conclusiones):
1. El edge crudo mejora con el bracket: 80/80 es el único positivo neto. Consistente con que
   los LVN del primer minuto producen movimientos grandes cuando funcionan.
2. ACCEPTANCE (continuación) > REJECTION en 80/80 — la hipótesis direccional H7 discrimina.
3. Frecuencia sobra (21 tr/mes global): hay margen para filtrar fuerte y quedar arriba del
   piso de 4/mes. El PF 2.0 requiere filtros → siguiente paso = ADN.

## Herramientas nuevas

- `evaluate_lvn_gates.py`: gates congelados, tabla año × métrica (estándar de reporte),
  cohortes por interacción, decisión de loop automática (exit code 0 = escalar temporada).
- `analyze_winner_dna.py`: winners vs losers por feature causal (37 features), separación
  estandarizada, bandas percentil 7.5–92.5 de winners (retener ~85%), WR dentro de banda.
  Exploratorio con look-ahead permitido; validación final era-blind + forward.

## ADN de winners — primer candidato que PASA gates (exploratorio, 2026-07-09)

`analyze_winner_dna.py` sobre los 127 eventos (bracket 80/80): la feature con mayor
separación estructural en ACCEPTANCE es la ubicación del LVN vs el value area contextual —
winners tienen el LVN MUY por debajo del VAH (mediana −167.5t) y losers por encima (+75t).
También separan: lvn_volume bajo (11 vs 26), delta_touch_bar positivo (+116 vs −137),
aggression_volume y tape_speed altos.

Regla estructural de 1 condición (no minada — primera feature del ranking de separación):

| Regla (bracket 80/80, 1:1) | n | tr/mes | WR% | PF | Gates |
|---|---:|---:|---:|---:|---|
| GLOBAL crudo | 105 | 21.0 | 53.3 | 1.14 | FAIL |
| ACCEPTANCE | 50 | 10.0 | 56.0 | 1.27 | FAIL (PF) |
| **ACCEPTANCE + LVN debajo del VAH ctx** | **33** | **6.6** | **69.7** | **2.30** | **PASS todos** |
| ACC + bajo VAH + delta_touch>0 | 18 | 3.6 | 83.3 | 5.00 | FAIL freq (capa opcional) |
| REJECTION + LVN debajo del VAH | 35 | 7.0 | 48.6 | 0.94 | FAIL — dirección importa |

Lectura económica: LVN del primer minuto ubicado debajo del valor de la premarket + precio lo
atraviesa con aceptación → continuación con recorrido de 80t. El espejo REJECTION no funciona,
consistente con que es un patrón direccional, no simetría mecánica.

Caveats obligatorios: n=33, UNA temporada, look-ahead exploratorio, condición elegida mirando
el ranking de ADN (in-sample). Según el loop congelado: candidato pasa gates → **se lanza
DST 2025** para validar fuera de esta muestra, y así hacia atrás hasta la frontera (~2022).

## Estado / siguiente

1. EN CURSO: reintento 13 fechas de junio (runner nuevo, Telegram activo).
2. Al completar: regenerar reporte temporada completa → gates de nuevo → `analyze_winner_dna`.
3. Si con ADN algún segmento filtrado pasa gates de forma robusta → lanzar DST 2025
   (2025-03-09 → 2025-11-01) y repetir hacia atrás hasta la frontera (~mediados 2022).
4. Meta: banco de eventos multi-año → setup congelado → backtest formal (costos, era-split,
   MC) → gate forward → port ATAS → cuenta Lucid $150k.
