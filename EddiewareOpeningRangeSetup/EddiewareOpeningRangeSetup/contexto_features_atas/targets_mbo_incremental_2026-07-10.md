# Targets — Valor incremental del order flow (MBP+tape) sobre el modelo LVN

Congelado: 2026-07-10. Estado: spec aprobado por usuario, implementación pendiente.

## Objetivo (del usuario, literal)

Determinar objetivamente si los datos de flujo de órdenes aportan información ADICIONAL a un
modelo basado en perfil de volumen / teoría de subasta / LVN minuto-1 / acceptance-rejection.
NO crear un edge de order flow: medir cuánto mejora el sistema estructural al agregarlo.
Hipótesis a comprobar: el edge nace del contexto de subasta; el order flow solo filtra ejecución.
Decisión que depende del resultado: comprar (o no) 5 años de datos + SSD + Databento.

## Realidad de los datos disponibles (inventariado 2026-07-10)

`data_footprint_generator\book_recordings\` (BookRecorder):
- `mbp_*.csv` (397 fechas): time_ny, side, price, volume — profundidad POR NIVEL (MBP).
- `tape_*.csv` (404 fechas): time_ny, price, volume, direction — ejecuciones con agresor.
- NO hay MBO puro (orden-por-orden). Los archivos 2023 tempranos solo cubren 09:25–09:31.
- **Fechas útiles (tape hasta ≥09:39): 113** — 2023×27, 2024×9, 2025×56, 2026×21.
  Ventana 09:25–09:40 = exactamente perfil minuto + retests.

### Mapeo honesto del wishlist de features

| Grupo pedido | ¿Derivable con MBP+tape? |
|---|---|
| Liquidez resting bid/ask | SÍ (MBP por nivel) |
| Consumo ejecutado bid/ask/total | SÍ (tape con direction) |
| Refill (cantidad/duración/intensidad) | SÍ por NIVEL (repoblado tras consumo) |
| Cancelaciones (retiro, velocidad, %) | PARCIAL: caída de volumen de nivel sin ejecución = retiro; no distingue órdenes individuales |
| Icebergs | PARCIAL (proxy): ejecutado en nivel >> visible sostenido; sin order-id no es detección real |
| Absorción | SÍ (proxy: consumo alto + precio no avanza) |
| Velocidad (contratos/s, ticks/s, antes/durante/después) | SÍ (tape) |
| Agresión (mkt buy/sell, delta, delta acumulado) | SÍ (tape) |
| Profundidad (niveles consumidos, liquidez removida) | SÍ (MBP+tape) |
| Tiempo (en LVN, a rechazo/continuación, toques) | SÍ (ya en el motor + refinable a ms) |
| Prioridad de cola / vida de orden individual | NO — eso sí requiere MBO real (Databento) |

## Protocolo congelado

1. **Eventos idénticos**: los del detector LVN (banco `_v4`), restringidos a las 113 fechas
   con cobertura. Cero cambios de reglas/horarios/umbrales. Merge por fecha+timestamp.
2. **Modelo A (baseline)**: features estructurales actuales (perfiles, POC/VAH/VAL, LVN/HVN,
   shape, distancias, interacción) — el CatBoost multi-tamaño ya construido.
3. **Modelo B**: mismos eventos, mismas features + SOLO las de order flow.
   REGLA ANTI-LEAK (PROGRESO_16): toda feature de flujo se corta en la CONFIRMACIÓN de
   entrada. Ventanas: pre-retest (aproximación), durante zona (touch→confirmación). Las
   ventanas "después" solo para descripción, jamás como feature de modelo.
4. **Comparación** en las mismas particiones era-blind (dev 2023-2025, val 2026, o CV por
   fecha dada la n): AUC por tamaño de winner, WR/PF/expectancy/MAE/MFE/DD/Sharpe/frecuencia/
   RR efectivo/distribuciones con el corte de score idéntico en A y B.
5. **Importancias**: FI + SHAP + permutation en ambos; qué agrega B, qué features de flujo
   aportan y cuáles no.
6. Sin lookahead, sin optimizar umbrales post-resultados, AMBIGUOUS jamás resuelto por
   suposición.

## Criterio de decisión (congelado ANTES de ver resultados)

- Mejora pequeña/marginal o inconsistente entre años → NO comprar 5 años de MBO.
- Mejora clara y consistente (ej. ΔAUC sostenido en val + mejora simultánea de PF y DD sobre
  eventos idénticos) → comprar SSD + Databento + histórico completo.
- Advertencia de contexto: el baseline A hoy es ~azar (AUC 0.43-0.50, PROGRESO_17). Si B
  levanta materialmente sobre eventos idénticos, el order flow ES la información faltante y
  la compra se justifica sola. Si B también queda en azar, la hipótesis LVN-minuto-1 queda
  refutada también con flujo, y se decide C/D del PROGRESO_17.

## Nota de muestra

113 fechas ≈ ~150-170 eventos con flujo (estimar exacto al hacer el merge). Suficiente para
el test incremental PAREADO (mismos eventos con/sin flujo); insuficiente para conclusiones
por subgrupo fino — reportar intervalos, no puntos.

## Entregables finales (agregados por el usuario, 2026-07-10)

1. **Tabla por variable de flujo** (no solo sí/no):
   `Variable | Importancia | Incremento PF | Incremento WR | Comentario (Mantener/No aporta)`
   por GRUPO de features (refill, velocidad, delta/agresión, profundidad/liquidez,
   absorción, cancelación-proxy) — incremento marginal A+grupo vs A y B−grupo vs B.
   Objetivo: si el 80% del valor viene de 2 grupos, al comprar Databento se sabe exactamente
   qué explotar.
2. **Informe de decisión** con recomendación explícita basada en los criterios congelados:
   - Comprar Databento: Sí / No
   - Nivel de confianza: Bajo / Medio / Alto
   - Mejora absoluta y relativa de PF, WR, MAE y DD (A vs B, mismos eventos, mismo corte)
   - Qué features de flujo aportaron y cuáles no
   - Estimación del beneficio esperado de ampliar el histórico 1→5 años (escalado de n y
     de intervalos de confianza)

Postura congelada: el proceso debe poder decir NO — si B también es azar, LVN-minuto-1 queda
refutado incluso con flujo y se ahorra la compra.

## Plan de implementación

1. `orderflow_features.py`: parser MBP+tape → features por evento (ventanas causales).
2. Merge con `LVN_Events` de las 113 fechas → `bank_orderflow.csv`.
3. `catboost_ab_orderflow.py`: protocolo A/B + métricas + FI/SHAP/permutation.
4. PROGRESO_18 con veredicto + Telegram.
