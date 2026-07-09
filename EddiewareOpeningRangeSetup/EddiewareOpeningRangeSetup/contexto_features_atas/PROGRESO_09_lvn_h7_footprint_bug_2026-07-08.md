# PROGRESO 09 — H7 aceptación/rechazo, ADN winners, bug footprint step (2026-07-08)

## 1. H7 implementada: dirección por aceptación/rechazo de valor

Reemplaza la dirección por procedencia (H6) como regla oficial del motor. Detalle completo en
`LVN_Retest_Research_Engine_2026-07-08.md` y `targets_lvn_volume_profile.md` (H7).

- `ACCEPTANCE` (atraviesa toda la zona) → `CONTINUATION`.
- `REJECTION` (frena y regresa) → `REVERSAL`.
- `UNRESOLVED` si no confirma antes de 09:40.
- Outcome empieza en la confirmación, medido desde `entry_price`.
- Smoke test 2/2 (sintético) OK: ACCEPTANCE/SHORT y REJECTION/LONG, ambos TP.
- Nuevo param `--resolution-confirm-ticks` (default 1).

## 2. ADN de ganadores (nuevas columnas outcome)

- `mae_before_mfe_ticks`: adverso sobrevivido antes de la máxima extensión (SL real del winner).
- `max_pullback_before_mfe_ticks`: retroceso máx desde el pico favorable camino al MFE.
- `rr_max_achievable = MFE / max(mae_before_mfe, 1 tick)`.
- `time_to_mfe_seconds` (ya existía): tiempo a máxima extensión.

## 3. Agresión (confirmación, no filtro)

Decisión: solo features que aplican a volume profile — delta, delta change, volume,
imbalances, speed, vPOC/VAH/VAL (ya cubiertos por distancias). NO se importó el resto de
`features\*.cs` (microstructure completa, DOM heatmap, etc. — no aplican a este análisis).

- `tape_speed_trades_per_second` (requiere `bar_trades`, nuevo en export CSV).
- `aggression_volume_per_second`, `aggression_delta_per_second`.
- `delta_touch_bar`, `delta_prev_bar`, `delta_change_touch_bar`.

## 4. Indicador C# — hasta 3 áreas LVN + bar_trades

`13_Volume_Profile_Eddieware.cs`: `FindLvnCandidates` reemplaza `FindBestLvn` (top-N por
score, `MaxLvnAreas` default 3, LVN1 más grueso/profundo). Export CSV agrega columna
`bar_trades`. **Compilado y desplegado**: DLL hash `039EFBE0` en Indicators + Strategies.
Requiere reiniciar ATAS para cargar.

## 5. Runner: días hábiles + replay corto + default preview

`lvn_OR_strategy_replay.py`:
- Feriados NYSE/CME auto-excluidos (`us_market_holidays`, override `--include-holidays`).
- Default = preview (`prepare-only`); captura real requiere `--run`.
- **Ventana replay corta**: `09:29–09:50` (antes `08:29–09:42`) — el contexto 08:30-09:30 se
  lee de la historia que ATAS ya carga al abrir el replay, ~5x más rápido. REGLA INTOCABLE:
  X1/X10 sigue igual, solo cambió el rango horario.
- Flags nuevos `--replay-from`/`--replay-to`; warning si `context_ok=False`.
- `compare_context_parity.py`: script de paridad FULL vs SHORT (pendiente correr formalmente,
  pero el piloto ya mostró filas 08:30→09:39 con replay arrancando en 09:29 — indicio fuerte
  de que la historia sí trae el contexto).

## 6. BUG BLOQUEANTE encontrado y diagnosticado: footprint step = 5 ticks

Piloto 2 fechas (2026-06-01, 2026-06-02): captura OK 2/2, pero **0 LVN, 0 eventos** en ambas.

Causa raíz: el chart NQ exporta niveles de footprint cada **1.25 (5 ticks)**, no 0.25 (1 tick)
— confirmado contando 48 niveles en el minuto 09:30-09:31 con paso exacto 1.25. El motor
Python arma bins con `tick_size=0.25`; cada nivel real cae aislado 5 bins aparte → todos los
candidatos LVN fallan `NEIGHBORS_HAVE_NO_VOLUME`. No es bug del indicador/motor: es
configuración del row/cell size del footprint en el chart ATAS.

**Fix decidido con el usuario**: cambiar el row size del chart a 1 tick (no adaptar el motor a
1.25 — perdería la precisión de 1 tick que pide el plan). Pendiente que el usuario lo ajuste
en ATAS; luego re-lanzar piloto de 2 fechas para confirmar LVN > 0 antes de escalar al mes.

## 7. Metodología de calibración confirmada con el usuario

"Empezar desde los ejemplos de libro (casos limpios ACCEPTANCE/REJECTION, alta confianza de
shape) y luego ir bajando el % de tolerancia del perfil" — ya está en
`targets_lvn_volume_profile.md` §"Calibración de tolerancias por entradas ganadoras" (punto
1b): validar lógica con casos textbook primero, luego encontrar el piso de confianza donde
WR/R:R todavía se sostiene, sin exigir shapes perfectos.

## 8. Reglas nuevas de flujo de trabajo (guardadas en memoria)

- Look-ahead SÍ se vale en exploración/investigación (no en validación final).
- Notificar avances por Telegram sin que se pida cada vez.
- Imágenes de valor (setups, hipótesis) en `C:\Users\k_99_\Desktop\imagenes_IA\`.
- Shape imperfecto ≠ filtro: muchos perfiles feos igual ganan (regla anti-perfección).
- **Cada hallazgo importante o actualización de plan → crear/actualizar un .md** (esta regla).

## Siguiente paso

1. Usuario ajusta row size del chart NQ a 1 tick.
2. Re-lanzar piloto `--dates 2026-06-01 2026-06-02 --run --force`.
3. Verificar `lvns > 0` y `events > 0` en el reporte.
4. Si pasa → lanzar captura mes junio completo (`--date-source weekdays --from-date 2026-06-01
   --to-date 2026-06-30 --run`).
5. Avisar por Telegram en cada hito.
