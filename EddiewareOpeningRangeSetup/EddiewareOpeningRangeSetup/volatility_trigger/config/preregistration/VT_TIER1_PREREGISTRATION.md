# Prerregistro VT Tier 1 trade

Fecha de congelado: 2026-07-26

Estado inicial: `PREREGISTERED_BEFORE_VT_OUTCOMES`

Enmienda técnica A1: `TECHNICAL_AMENDMENT_AFTER_SMOKE_BEFORE_DISCOVERY`.
La enmienda no cambia detector, candidatos, features, outcome, modelo, gates ni
splits. Su justificación, reglas y evidencia están congeladas en
`AMENDMENT_001_TIMESTAMP_AND_RUNTIME.md`.

## Pregunta

Después de que el detector congelado publique un `Liquidity Burst`, ¿las
familias Rhythm, DVA, Acceptance, VWAP, Order Flow, Footprint, Delta Levels y
AMT aportan información causal incremental para identificar una trayectoria
`SNIPER_SUCCESS`?

## Evento raíz

Se reproduce la fórmula, los umbrales y la máquina causal del núcleo de
detección de `12_LiquidityBurstDetector.cs`, versión
`liquidity-burst-detector-2026-07-22-v7-postburst-matrix`. No se cambian
umbrales, ventanas, dirección, cooldown ni población.

La fuente de esta corrida es el caché ATAS local. No se exige identidad de
precio o velocidad tick a tick con exports de replays antiguos de otra versión:
la regresión de control sí debe reproducir tiempo, lado, delta y cambio de delta
del evento conocido. El control 2022-04-05 09:32 BUY reprodujo
`Delta1s=273`, `Delta3s=338` y `DeltaChange1s=225`.

El tiempo cero causal no es el inicio del bucket que retrospectivamente contiene
el burst. Es el primer timestamp posterior que cierra/publica dicho bucket:
`DetectorPublishTimestamp`.

## Primera representación

`tier1_trade` utiliza trades ATAS, agresor, precio y volumen. No utiliza DOM.
Esto permite probar primero las familias Tier 1 que no requieren reconstrucción
de libro. Profundidad/microprice se reserva como bloque incremental separado y
no puede rescatar retrospectivamente un fallo de Tier 1 sobre el mismo split.

Precio analítico primario: último trade conocido en `t0`. Esta corrida es
científica, no una simulación de fill.

## Candidatos

- Rejilla de 50 ms desde `DetectorPublishTimestamp` hasta +5 s, extremos
  incluidos.
- Dos direcciones causales por candidato: BUY y SELL.
- Cada fila conserva `max_feature_timestamp <= candidate_timestamp`.
- El agrupamiento estadístico es por `LB_ID` y sesión; nunca se dividen filas al
  azar.

## Outcome primario

`SNIPER_SUCCESS=1` si se cumplen simultáneamente:

- `TimeToImpulse_4t <= 750 ms`;
- desplazamiento firmado a 1 s `>=4 ticks`;
- desplazamiento firmado a 2 s `>=8 ticks`;
- excursión adversa anterior a 4 ticks `<=2 ticks`;
- MFE inicial antes de pullback de 3 ticks `>=8 ticks`;
- eficiencia direccional a 2 s `>=0.65`.

Todos los outcomes usan únicamente eventos posteriores a `t0` y nunca aparecen
en la matriz de predictores.

## Familias

- Base: atributos congelados del LB, tiempo desde LB, velocidad y trade rate.
- Rhythm: aceleración del trade rate, compresión interarrival, racha agresora y
  acuerdo multiescala.
- DVA: posición normalizada, distancia a POC/VAH/VAL y migración POC a 30 s.
- Acceptance: retención tiempo/volumen respecto a `LB_Price`.
- VWAP: distancia z, pendiente y reclaim/hold causales.
- Order Flow: delta/agresión, impacto y esfuerzo sin progreso.
- Footprint: imbalances diagonales 3:1 y esfuerzo/resultado por precio.
- Delta Levels: distancia a extremos de delta y extremo sin progreso.
- AMT: balance e imbalance cuantitativos.

No se prueban combinaciones arbitrarias. Cada familia se añade individualmente
al modelo base. El modelo conjunto contiene únicamente familias que pasan sus
gates discovery.

## Splits y apertura

- Discovery: 2022-04-04 a 2022-12-30.
- Validation: 2023-01-03 a 2023-12-29; no se abre si discovery falla.
- Holdout: 2024-01-02 a 2024-12-31; no se abre si validation falla.
- 2025–2026 permanece cerrado.

Dentro de discovery se usan folds mensuales expandibles. El modelo es regresión
logística L2 con imputación mediana, estandarización y balanceo de clases.

## Gates discovery

1. Al menos 80 LBs y 20 LBs con alguna trayectoria `SNIPER_SUCCESS`, presentes
   en al menos tres meses.
2. AUC candidato del mejor modelo `>=0.60`.
3. Límite inferior bootstrap 95% del AUC `>0.50`, remuestreando por LB.
4. Una familia se conserva sólo si añade `>=0.02` AUC y `>=10%` PR-AUC relativo
   frente a base, con lift positivo en al menos 75% de folds.
5. Debe superar baselines de LB inmediato, delays fijos, velocidad, trade rate y
   azar.

Un fallo detiene la apertura de 2023.

## Integridad

- Sin TP/SL/PnL.
- Sin MFE/MAE de estrategia como predictor.
- Sin normalización futura.
- Sin selección del mejor candidato retrospectivo para medir el trigger.
- Sin modificar `02_Visual_Logic.cs`.
- Los hallazgos y resultados de pruebas se notifican por Telegram.
- El orden causal primario de los trades es el orden de archivo. Los retrocesos
  aislados aceptados se corrigen únicamente con
  `EffectiveTimestamp_i=max(EffectiveTimestamp_i-1, RawTimestamp_i)`, por lo que
  ningún trade se adelanta.
- Una sesión sólo admite esa corrección si contiene como máximo 10 retrocesos y
  ninguno supera 50 ms; fuera de esos límites se excluye completa.

`INFORMATION_STATUS=VT_TIER1_A1_PREREGISTERED_DISCOVERY_2022_SEALED`
