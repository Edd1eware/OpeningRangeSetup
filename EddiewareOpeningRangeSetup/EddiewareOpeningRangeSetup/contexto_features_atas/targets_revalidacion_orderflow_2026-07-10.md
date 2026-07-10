# Targets — REVALIDACIÓN del valor incremental del order flow (spec usuario 2026-07-10)

Estado: congelado. Pregunta única: ¿la profundidad de liquidez y el delta mejoran de manera
ESTABLE el desempeño del setup LVN sobre los mismos eventos? Prioridad: aumentar muestra con
grabaciones nuevas del BookRecorder en replay; NO comprar Databento aún; NO estrategia nueva.

## Reglas metodológicas (congeladas, del usuario)

Sin cambiar hipótesis/brackets/umbrales; sin filtros nuevos antes de repetir; sin optimizar;
sin selección manual de días; sin descartar eventos fallidos; sin redefinir retest. La
recaptura solo sirve para: +fechas con libro+cinta → repetir el MISMO experimento → ver si
profundidad_liquidez mantiene su valor → estabilidad temporal → decidir compra SSD+MBO 5 años.

Referencia del experimento previo: PROGRESO_18 (40/40: A PF 1.22 → B PF 1.63; 80/80
inconsistente; ~80% del valor en profundidad_liquidez; delta moderado; proxies de refill/
absorción/cancelación sin valor; muestra insuficiente; compra: todavía no).

## Datos: NO es MBO puro (MBP + tape)

Excluir toda feature que requiera MBO real (ID por orden, cancelación individual, prioridad
de cola, icebergs confirmados, refill por orden). Los proxies se etiquetan SIEMPRE como
proxies, jamás como información MBO real.

## Ventanas

- Perfiles y retest: las congeladas del motor (08:30–09:30 / 09:30–09:31 / 09:31–09:40 ET,
  DST correcto).
- Extracción de flujo RELATIVA AL PRIMER TOQUE, tamaños configurables SIN optimizar:
  pre-touch [-10s,-1s), touch [-1s,+3s), post-inmediato [+3s,+10s), post-extendido
  [+10s,+30s). Nota causal: con confirmación al cierre de la barra 1-min del retest, las
  ventanas hasta +30s ocurren ANTES de la confirmación → usables como features de modelo
  sin leak (verificar por-evento: ventana debe terminar ≤ instante de confirmación; si no,
  recortar o excluir y auditar).

## PARTE 1 — Validación de grabaciones (NUEVO, a implementar)

Por fecha: inicio/fin reales de book y tape; % cobertura 09:25–09:40; # snapshots/updates/
trades; gaps máximo y conteos >1s/>5s/>10s; duplicados; timestamps fuera de orden; niveles
inválidos; volúmenes negativos; resets; símbolo/roll; estado final
(FULL_COVERAGE / PARTIAL_COVERAGE / MISSING_BOOK / MISSING_TAPE / TIMESTAMP_GAPS /
BAD_SYMBOL / DUPLICATED_DATA / INVALID_SESSION). Ninguna exclusión silenciosa: archivo de
auditoría con motivo por fecha.

## PARTE 2 — Eventos estructurales

Lógica congelada del banco `_v4` sin cambios (salvo bug demostrado). Todos los retests, sin
selección visual, mismos criterios de toque/tolerancia/acceptance/rejection/invalidación.

## PARTE 3 — Pareo eventos ↔ flujo

Vincular retest con book+tape; verificar cobertura alrededor del toque; si falta: el evento
QUEDA en el banco estructural, marcado no-elegible para el A/B con razón registrada.
`event_id` estable = fecha + símbolo + timestamp_retest + precio_lvn + dirección + índice
(el actual del motor ya cumple: fecha+lvn_id+número de retest; se le añade dirección).

## PARTE 3 (completa, recibida 2026-07-10) — Pareo con auditoría

1. Detector estructural primero, sin flujo (ya existe: banco `_v4`).
2. Vincular book+tape en ventanas configurables alrededor del retest (pre/touch/post).
3. **Auditoría de cobertura POR EVENTO** (nuevo): `book_available`, `tape_available`,
   `coverage_percent`, `largest_gap_seconds`, `book_updates`, `trade_count`, `quality_flag`.
4. **Exclusión controlada** (nuevo): evento sin flujo suficiente queda en el banco
   estructural con `excluded_from_orderflow=TRUE` + razón (NO_BOOK / NO_TAPE /
   BAD_TIMESTAMPS / LOW_COVERAGE / CORRUPTED_DATA / UNKNOWN) → `events_excluded_audit.csv`.
   Jamás eliminar en silencio.
5. **event_id versión spec** (ajuste): fecha_símbolo_DIRECCIÓN_hhmmss_precio_R# (el actual
   fecha+lvn_id+R# gana el campo dirección; mapping 1:1 conservado).
6. **Integridad A/B** (nuevo): `ab_dataset_integrity.csv` con totales, excluidos, duplicados,
   sin-pareo, repetidos y HASH de Dataset A y B.
7. **Congelamiento**: creado el conjunto A/B no se modifica nada (ids/targets/labels/reglas/
   horarios/ventanas/criterios); cualquier cambio = versión nueva del dataset.

## PARTE 4 (completa, recibida 2026-07-10) — Dataset A estructural

- Features: las listas del usuario (contexto 08:30-09:30, minuto 09:30-09:31, distancias,
  variables del retest, temporales) — ~95% ya existen en el Profile Feature Engine (`_v4`,
  187-194 columnas); faltantes menores a agregar: VWAP del perfil contextual como nivel,
  volume-at-POC explícito, largest HVN/LVN width, penetración máxima del retest, opening
  type, régimen de volatilidad etiquetado.
- **Variables de resultado SEPARADAS** (nuevo empaque): Winner/Loser, MFE, MAE, TP/SL por
  bracket, drawdown, runup, duración → archivo/columnas aparte, jamás en el set de
  entrenamiento (hoy conviven en el mismo CSV; el A/B ya las excluye por whitelist, pero el
  spec exige separación física).
- **`feature_cutoff_audit.csv`** (nuevo): por feature — nombre, fuente, ventana inicio/fin,
  available_before_entry, leakage_risk, notas. Precedente directo: leak de agresión cazado
  en PROGRESO_16.
- Prohibición anti-lookahead total para entrenamiento (ya política del pipeline; ahora
  auditable por archivo).

## Estado de ejecución

- BLOQUEADOR: BookRecorder aún no escribe en los replays (verificación del indicador en el
  chart pendiente del usuario; cero `bookrec_status_*` jamás escritos).
- Al confirmarse: sanity 1 fecha → recaptura 2022 completo (150) + 2024 completo (165)
  ≈ 11-12h con vigilancia y Telegram; luego Partes 1→4.
