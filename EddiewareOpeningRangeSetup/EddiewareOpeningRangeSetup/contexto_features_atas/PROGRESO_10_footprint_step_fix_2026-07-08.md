# PROGRESO 10 — fix estructural footprint step + 5 zonas LVN (2026-07-08)

## Contexto

Piloto anterior (`PROGRESO_09`) encontró bloqueante: chart exporta footprint a 5 ticks/fila
(paso 1.25) en vez de 1 tick (0.25). El usuario intentó corregirlo en el chart de ATAS, pero el
ajuste **no se mantuvo** (recaptura de 2026-06-01 seguía en 1.25 exacto). En vez de depender de
un ajuste manual de UI que ya falló dos veces, se resolvió a nivel de motor.

## Fix implementado: detección automática del grid nativo de precio

**Python (`lvn_retest_engine/profile_builder.py`)**: nueva función `detect_level_step(prices,
tick_size)` — calcula la moda de los saltos entre precios únicos observados en la ventana y usa
ESE step (no `config.tick_size` fijo) para construir los bins del perfil. `Profile.tick_size`
pasa a representar el grid nativo detectado por perfil; `config.tick_size` se mantiene como tick
real del instrumento para todas las columnas `*_ticks` (que ya operaban sobre precios reales, sin
cambio). Propagado a `lvn_detector.py` y `hvn_detector.py` (conversión bin→precio y `width_ticks`
escalado a ticks reales vía `levels_per_tick = level_step / tick_size`).

**C# (`13_Volume_Profile_Eddieware.cs`)**: mismo problema estructural existía en vivo (el
indicador armaba bins con el tick real fijo, así que la línea LVN en el chart tampoco iba a
aparecer). Refactor: `CollectCandleLevels` junta niveles crudos (precio, volumen) en vez de
binear directo; `DetectLevelStep` (mismo algoritmo que Python) calcula el grid nativo por
ventana (contexto y minuto por separado); `BinLevels` arma el diccionario con ese step. Todas las
conversiones bin→precio (`UpdateDirectionOutputs`, `UpdateLvnOutputs`, `FindLvnCandidates`) usan
el step detectado; `DirRangeTicks` se reescala a ticks reales. Requiere `using System.Linq;`
(agregado).

**Resultado**: funciona sin importar si el chart está en 1 tick, 5 ticks o cualquier otro row
size — no depende de configuración manual de ATAS que puede resetearse.

## MaxLvnAreas 3 → 5

Por pedido del usuario: "extiende tus intentos de ubicar la zona a 5". `MaxLvnAreas` default 5
(antes 3), cap interno actualizado en `FindLvnCandidates` (Python ya soportaba N vía
`minute.lvns` completo; el límite de 3 era solo del overlay visual C#).

## Compilación y despliegue

0 errores. DLL desplegado: hash `1b1279909f9e` en `ATAS\Indicators` y `ATAS\Strategies`.
Requiere reiniciar ATAS para cargar.

## Verificación offline (reprocesando CSV real ya capturado, 2026-06-01)

Con el fix, `NEIGHBORS_HAVE_NO_VOLUME` desaparece por completo de `Debug.csv` — confirma que la
causa estructural quedó resuelta. Resultado tras el fix:

| Perfil | Candidatos | Aceptados | Razón dominante restante |
|---|---:|---:|---|
| CONTEXT_0830_0930 | 164 | 1 | `ABOVE_NEIGHBOR_PERCENT_LIMIT` (contenido real) |
| FIRST_MINUTE_0930_0931 | 48 | 0 | `NOT_LOWER_THAN_BOTH_SIDES` / `ABOVE_NEIGHBOR_PERCENT_LIMIT` (contenido real) |

0 aceptados en el perfil del minuto para ESTE día específico ya no es bug — es una medición real
de frecuencia con n=1, exactamente lo que Fase A debe cuantificar sobre muchos días. **No se
tocan los umbrales default con una sola fecha** (regla anti-optimización sobre la misma muestra,
ya congelada en `targets_lvn_volume_profile.md`).

## Siguiente paso

1. Recapturar 2026-06-01 con el DLL nuevo (en curso, background) — confirma extremo a extremo:
   CSV con `bar_trades`, hasta 5 líneas LVN en el chart si detecta, pipeline Python limpio.
2. Lanzar julio 2026 completo (`--date-source weekdays --from-date 2026-07-01 --to-date
   2026-07-31 --run`) para tener muestra suficiente y medir frecuencia real de LVN/retest antes
   de tocar cualquier umbral.
3. Avisar por Telegram.
