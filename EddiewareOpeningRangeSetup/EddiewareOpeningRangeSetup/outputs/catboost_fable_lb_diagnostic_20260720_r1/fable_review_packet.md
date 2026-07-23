# Independent review request for Claude Fable

You are reviewing a causal microstructure study. Do not fit or claim a deployable model. The 2025-2026 holdout has already been opened and may only generate hypotheses.

Objective: after detecting a Liquidity Burst, at the original causal decision callback (no 1/3/5-second wait), distinguish true absorption A from clean breakout B. Mixed C is abstention.

Tasks:
1. Audit whether CatBoost found genuine incremental nonlinear information or only small-sample instability.
2. Explain the 2022-2024 to 2025-2026 sign reversal mechanistically.
3. Propose at most 8 genuinely new causal features, not aliases of fields already present. For each give exact formula, source, causal window, availability timestamp, expected A-vs-B direction, physical rationale, redundancy check, and falsification test.
4. Prioritize features that can anticipate at the callback. Do not use post-burst response, MAE/MFE/result, delayed confirmation, or MBO unless the evidence makes it indispensable.
5. Return a clear STOP/CONTINUE decision for feature engineering and name the minimum next experiment. Be skeptical of n=115 and of SHAP as validation.

## CatBoost report

# Diagnóstico CatBoost — Liquidity Burst A vs B

## Alcance

- Discovery 2022–2024: 70 A/B.
- Corrida abierta 2025–2026: 45 A/B.
- Esta investigación es posterior a abrir el holdout. Sirve para generar hipótesis; no crea una nueva validación.
- CatBoost usa profundidad 2, regularización L2 fuerte y parámetros fijos; no se optimiza contra 2025–2026.
- Respuestas 1/3/5 s y campos de outcome no entran como predictores.

## Desempeño temporal

| Corte | Features | n | AUC | Balanced acc. | p permutación |
| --- | --- | ---: | ---: | ---: | ---: |
| DISCOVERY_TO_NEW | CORE_FROZEN | 45 | 0.384 | 0.333 | 0.9414 |
| DISCOVERY_TO_NEW | BURST_MECHANISM | 45 | 0.436 | 0.433 | 0.8422 |
| DISCOVERY_TO_NEW | ALL_CAUSAL | 45 | 0.327 | 0.317 | 0.9860 |
| THROUGH_2025_TO_2026 | CORE_FROZEN | 11 | 0.067 | 0.183 | 0.9934 |
| THROUGH_2025_TO_2026 | BURST_MECHANISM | 11 | 0.333 | 0.383 | 0.8210 |
| THROUGH_2025_TO_2026 | ALL_CAUSAL | 11 | 0.200 | 0.183 | 0.9502 |

## Incremento frente al core

| Features | Delta AUC | Bootstrap 95% | P(delta>0) |
| --- | ---: | ---: | ---: |
| ALL_CAUSAL | -0.058 | [-0.249, +0.140] | 0.277 |
| BURST_MECHANISM | +0.051 | [-0.113, +0.216] | 0.723 |

## Features univariadas estables

Candidatas que pasan todos los criterios: **0**.

| Feature | Familia | AUC old | AUC new | 2025 | 2026 | BUY | SELL | q |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Realized_Volatility_10s_Ticks | BURST_INTENSITY | 0.594 | 0.708 | 0.727 | 0.400 | 0.463 | 0.889 | 0.995 |
| Realized_Volatility_60s_Ticks | BURST_INTENSITY | 0.559 | 0.704 | 0.693 | 0.400 | 0.481 | 0.873 | 0.995 |
| Realized_Volatility_30s_Ticks | BURST_INTENSITY | 0.588 | 0.686 | 0.722 | 0.400 | 0.420 | 0.929 | 0.995 |
| Dist_OR_Low_Ticks | AUCTION_CONTEXT | 0.559 | 0.671 | 0.753 | 0.467 | 0.519 | 0.611 | 0.995 |
| Flow_3_5_GrossAggressive | FLOW_PERSISTENCE | 0.615 | 0.670 | 0.818 | 0.400 | 0.685 | 0.675 | 0.995 |
| Dist_VAL_Ticks | BURST_INTENSITY | 0.561 | 0.659 | 0.738 | 0.400 | 0.469 | 0.591 | 0.995 |
| Flow_3_5_DirectionalVelocityTPS | FLOW_PERSISTENCE | 0.571 | 0.642 | 0.627 | 0.533 | 0.512 | 0.714 | 0.995 |
| Dist_VWAP_Ticks | AUCTION_CONTEXT | 0.553 | 0.642 | 0.760 | 0.367 | 0.457 | 0.532 | 0.995 |
| Dist_OR_High_Ticks | AUCTION_CONTEXT | 0.548 | 0.639 | 0.756 | 0.333 | 0.426 | 0.548 | 0.995 |
| BreakOut_TICKS_PER_SEC_AtEntry | BURST_INTENSITY | 0.549 | 0.620 | 0.662 | 0.533 | 0.481 | 0.690 | 0.995 |
| Pre_Approach_Velocity_TPS | CROSSING_ANATOMY | 0.600 | 0.613 | 0.620 | 0.350 | 0.389 | 0.782 | 0.995 |
| Velocity_Retention_3_5 | FLOW_PERSISTENCE | 0.573 | 0.604 | 0.582 | 0.520 | 0.516 | 0.605 | 0.995 |
| Signed_Previous_Delta_Share_AtEntry | BURST_INTENSITY | 0.541 | 0.590 | 0.629 | 0.417 | 0.506 | 0.730 | 0.995 |
| Profile_Excess_Kurtosis | AUCTION_CONTEXT | 0.574 | 0.571 | 0.596 | 0.533 | 0.568 | 0.540 | 0.995 |
| signed_velocity_3s | BURST_INTENSITY | 0.584 | 0.563 | 0.604 | 0.267 | 0.389 | 0.683 | 0.995 |

## SHAP fuera de muestra — ALL_CAUSAL

| Rango | Feature | Familia | Mean abs SHAP | Corr(value, SHAP) | SHAP A-B |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | Flow_1_3_CounterflowShare | FLOW_PERSISTENCE | 0.4603 | 0.668 | -0.0192 |
| 2 | Previous_Delta_AtEntry | BURST_INTENSITY | 0.3957 | -0.706 | -0.2600 |
| 3 | mean_trade_size | BURST_INTENSITY | 0.1828 | -0.830 | -0.0126 |
| 4 | Profile_Local_Maxima_Count | AUCTION_CONTEXT | 0.1694 | 0.838 | -0.0348 |
| 5 | Directional_VWAP_Distance_Ticks_AtEntry | AUCTION_CONTEXT | 0.1216 | 0.933 | -0.1555 |
| 6 | PreEntry_Volume_Climax_Ratio_AtEntry | BURST_INTENSITY | 0.1113 | 0.813 | -0.0207 |
| 7 | PreEntry_Directional_Efficiency3_AtEntry | BURST_INTENSITY | 0.0913 | 0.399 | -0.0059 |
| 8 | Nearest_OR_Edge_Distance_Ticks_AtEntry | AUCTION_CONTEXT | 0.0850 | 0.642 | -0.0481 |
| 9 | BuySellRatio | BURST_INTENSITY | 0.0830 | -0.803 | -0.0326 |
| 10 | Flow_3_5_GrossAggressive | FLOW_PERSISTENCE | 0.0824 | 0.788 | +0.0453 |
| 11 | Flow_3_5_CounterflowShare | FLOW_PERSISTENCE | 0.0738 | -0.882 | +0.0981 |
| 12 | Short_Long_Volatility_Ratio | BURST_INTENSITY | 0.0727 | 0.726 | -0.0215 |
| 13 | Velocity_Retention_1_3 | FLOW_PERSISTENCE | 0.0692 | 0.875 | -0.0040 |
| 14 | Previous_Volume_AtEntry | BURST_INTENSITY | 0.0666 | -0.663 | -0.0506 |
| 15 | Flow_3_5_DirectionalNetDelta | FLOW_PERSISTENCE | 0.0541 | 0.796 | +0.0168 |

## Familias

| Familia | Modo | Features | AUC new |
| --- | --- | ---: | ---: |
| ACCEPTANCE_REJECTION | ONLY_FAMILY | 2 | 0.563 |
| EFFORT_RESULT | ONLY_FAMILY | 2 | 0.547 |
| FLOW_PERSISTENCE | ONLY_FAMILY | 19 | 0.500 |
| CROSSING_ANATOMY | ONLY_FAMILY | 3 | 0.496 |
| AUCTION_CONTEXT | ONLY_FAMILY | 23 | 0.436 |
| LEVEL_MEMORY | ONLY_FAMILY | 4 | 0.436 |
| BURST_INTENSITY | ONLY_FAMILY | 66 | 0.280 |
| BURST_INTENSITY | WITHOUT_FAMILY | 53 | 0.473 |
| ACCEPTANCE_REJECTION | WITHOUT_FAMILY | 117 | 0.358 |
| AUCTION_CONTEXT | WITHOUT_FAMILY | 96 | 0.344 |
| LEVEL_MEMORY | WITHOUT_FAMILY | 115 | 0.340 |
| CROSSING_ANATOMY | WITHOUT_FAMILY | 116 | 0.336 |
| FLOW_PERSISTENCE | WITHOUT_FAMILY | 100 | 0.318 |
| EFFORT_RESULT | WITHOUT_FAMILY | 117 | 0.316 |

## Regla de interpretación

CatBoost sólo demuestra información nueva si ALL_CAUSAL o BURST_MECHANISM supera al CORE fuera de era con delta positivo, intervalo bootstrap que no cruce cero y estabilidad en 2025/2026 y BUY/SELL. SHAP por sí solo explica el modelo; no valida una feature.


## Top CatBoost interactions

feature_1,feature_2,interaction_strength
Flow_1_3_CounterflowShare,Prior_Volume_At_Level_Band_60s,9.066308151324913
Nearest_OR_Edge_Distance_Ticks_AtEntry,mean_trade_size,6.14489854585769
Profile_Local_Maxima_Count,Previous_Delta_AtEntry,3.2399958739457992
BuySellRatio,Short_Long_Volatility_Ratio,2.9955132519431866
Flow_3_5_DirectionalNetDelta,Flow_3_5_GrossAggressive,2.666749175304707
PreEntry_Volume_Climax_Ratio_AtEntry,Realized_Volatility_30s_Ticks,2.644859326196021
Previous_Delta_AtEntry,Previous_Volume_AtEntry,2.309464608027562
PreEntry_Volume_Climax_Ratio_AtEntry,Flow_1_3_CounterflowShare,1.7361332536607388
PreBurst_Rotation_Index_10s,Flow_3_5_CounterflowShare,1.29705130571182
Cumulative_Delta_AtEntry,Previous_Delta_AtEntry,1.15365062832775
Directional_VWAP_Distance_Ticks_AtEntry,signed_acceleration_1s,1.0660823805869297
Previous_Delta_AtEntry,Volume_AtEntry,0.9113508756669856
directional_poc_distance,Cumulative_Delta_AtEntry,0.867657864185386
directional_poc_distance,Previous_Delta_AtEntry,0.8567880034660883
Delta10s,Delta_AtEntry,0.830462569367567
BuySellRatio,Flow_0_1_DirectionalVelocityTPS,0.8229635558040207
BuySellRatio,Delta_Change_AtEntry,0.8182953485493931
Previous_Delta_AtEntry,signed_acceleration_1s,0.7221938952070729
Cumulative_Delta_AtEntry,Flow_1_3_CounterflowShare,0.7205754285068626
directional_vwap_distance,Previous_Delta_AtEntry,0.713270673501516


## Existing causal feature dictionary (do not rename these as new)

feature,mechanism_family,source,formula,units,interpretation,window_start_seconds,window_end_seconds,coverage_old_pct,coverage_new_pct
PreBurst_Acceptance_Dwell_Ratio_5s,ACCEPTANCE_REJECTION,burst_events,seconds accepted beyond broken OR edge / observed seconds,ratio,Aceptación causal previa al burst.,-5,0,100.0,100.0
PreBurst_Reclaim_Count_10s,ACCEPTANCE_REJECTION,burst_events,crossings from accepted to reclaimed side,count,Reclaims causales antes del burst.,-10,0,100.0,100.0
Body_OR_Ratio_AtEntry,AUCTION_CONTEXT,trade_inputs,"abs(body ticks)/max(OR ticks,1)",ratio,Extensión del cuerpo normalizada por régimen.,-60,0,100.0,100.0
Directional_OR_Extension_Ticks_AtEntry,AUCTION_CONTEXT,trade_inputs,execution_sign*distance beyond execution-side OR edge,ticks,Extensión causal respecto al OR.,-600,0,100.0,100.0
Directional_VWAP_Distance_Ticks_AtEntry,AUCTION_CONTEXT,trade_inputs,execution_sign*(entry-vwap)/tick,ticks,Alineación de entrada con valor negociado.,-600,0,100.0,100.0
Dist_OR_High_Ticks,AUCTION_CONTEXT,burst_events,(price-OR_high)/tick,ticks,Ubicación respecto al OR high.,-60,0,100.0,100.0
Dist_OR_Low_Ticks,AUCTION_CONTEXT,burst_events,(price-OR_low)/tick,ticks,Ubicación respecto al OR low.,-60,0,100.0,100.0
Dist_POC_Ticks,AUCTION_CONTEXT,burst_events,(price-poc)/tick,ticks,Ubicación respecto al POC causal.,-1800,0,100.0,100.0
Dist_VWAP_Ticks,AUCTION_CONTEXT,burst_events,(price-vwap)/tick,ticks,Ubicación respecto a VWAP.,-1800,0,100.0,100.0
Nearest_OR_Edge_Acceptance_Ratio3_AtEntry,AUCTION_CONTEXT,trade_inputs,fraction prior 3 closed bars accepted outside nearest OR edge,ratio,Aceptación frente a rechazo del borde.,-240,-1,100.0,100.0
Nearest_OR_Edge_Distance_Ticks_AtEntry,AUCTION_CONTEXT,trade_inputs,"min(abs(entry-OR high),abs(entry-OR low))/tick",ticks,Proximidad al borde estructural más cercano.,-600,0,100.0,100.0
OR_WidthTicks,AUCTION_CONTEXT,burst_events,(OR_high-OR_low)/tick,ticks,Régimen de rango de apertura.,-60,0,100.0,100.0
Prior_Closed_ATR3_Ticks_AtEntry,AUCTION_CONTEXT,trade_inputs,mean true range of prior 3 closed bars,ticks,Volatilidad causal inmediata.,-240,-1,100.0,100.0
Prior_Closed_ATR5_Ticks_AtEntry,AUCTION_CONTEXT,trade_inputs,mean true range of prior 5 closed bars,ticks,Volatilidad causal suavizada.,-360,-1,100.0,100.0
Profile_Concentration,AUCTION_CONTEXT,burst_events,POC volume/total profile volume,ratio,Concentración modal sin etiqueta manual.,-1800,0,100.0,100.0
Profile_Effective_Nodes,AUCTION_CONTEXT,burst_events,exp(profile entropy),count,Número efectivo de niveles negociados.,-1800,0,100.0,100.0
Profile_Excess_Kurtosis,AUCTION_CONTEXT,burst_events,volume-weighted fourth standardized moment-3,ratio,Colas/concentración del perfil.,-1800,0,100.0,100.0
Profile_Local_Maxima_Count,AUCTION_CONTEXT,burst_events,count(local maxima in volume profile),count,Multimodalidad matemática.,-1800,0,100.0,100.0
Profile_Normalized_Entropy,AUCTION_CONTEXT,burst_events,profile entropy/log(number of price nodes),ratio,Dispersión de volumen entre niveles.,-1800,0,100.0,100.0
Profile_Position_Percentile,AUCTION_CONTEXT,burst_events,cumulative profile volume below price/total volume,ratio,Posición relativa dentro de la subasta.,-1800,0,100.0,100.0
Profile_Skewness,AUCTION_CONTEXT,burst_events,volume-weighted third standardized moment,ratio,Asimetría matemática del perfil.,-1800,0,100.0,100.0
Profile_Std_Ticks,AUCTION_CONTEXT,burst_events,volume-weighted profile standard deviation,ticks,Dispersión matemática del perfil.,-1800,0,100.0,100.0
directional_poc_distance,AUCTION_CONTEXT,engineered,burst_sign*Dist_POC_Ticks,ticks,Posición respecto a POC en dirección del burst.,-1800,0,100.0,100.0
directional_vwap_distance,AUCTION_CONTEXT,engineered,burst_sign*Dist_VWAP_Ticks,ticks,Posición respecto a VWAP en dirección del burst.,-1800,0,100.0,100.0
profile_confluence_4t,AUCTION_CONTEXT,engineered,count(abs(dist POC/VAH/VAL/HVN/LVN)<=4),count,Confluencia de niveles cerca del burst.,-1800,0,100.0,100.0
Acceleration1s,BURST_INTENSITY,burst_events,velocity1s_t-velocity1s_t-1,ticks/s2,Cambio de velocidad inmediato.,-2,0,100.0,100.0
Acceleration3s,BURST_INTENSITY,burst_events,velocity3s_t-velocity3s_t-1,ticks/s2,Cambio de velocidad suavizado.,-4,0,100.0,100.0
Body_AtEntry,BURST_INTENSITY,trade_inputs,body breakout at prediction,ticks,Desplazamiento del bar al decidir.,0,0,100.0,100.0
BreakOut_TICKS_PER_SEC_AtEntry,BURST_INTENSITY,trade_inputs,causal breakout speed,ticks/s,Velocidad del setup al decidir.,-60,0,100.0,100.0
BuySellRatio,BURST_INTENSITY,burst_events,buy_volume/sell_volume,ratio,Asimetría de agresores.,-1,0,100.0,100.0
Buy_Imbalance_Count_AtEntry,BURST_INTENSITY,trade_inputs,buy imbalance count,count,Desequilibrios compradores observados.,-60,0,100.0,100.0
ContractsPerSecond,BURST_INTENSITY,burst_events,"sum(volume,1s)",contracts/s,Intensidad de contratos.,-1,0,100.0,100.0
CumulativeDeltaWindow,BURST_INTENSITY,burst_events,"sum(delta,CumulativeWindowSeconds)",contracts,CVD causal del burst.,-3,0,100.0,100.0
Cumulative_Delta_AtEntry,BURST_INTENSITY,trade_inputs,session CVD at prediction,contracts,Régimen direccional causal.,-1800,0,100.0,100.0
Delta10s,BURST_INTENSITY,burst_events,"sum(delta, 10s)",contracts,Contexto pre-burst de 10 segundos.,-10,0,100.0,100.0
Delta1s,BURST_INTENSITY,burst_events,"sum(delta, 1s)",contracts,Agresión neta del segundo del burst.,-1,0,100.0,100.0
Delta2s,BURST_INTENSITY,burst_events,"sum(delta, 2s)",contracts,Persistencia corta de agresión.,-2,0,100.0,100.0
Delta3s,BURST_INTENSITY,burst_events,"sum(delta, 3s)",contracts,Persistencia de agresión a 3 segundos.,-3,0,100.0,100.0
Delta5s,BURST_INTENSITY,burst_events,"sum(delta, 5s)",contracts,Persistencia de agresión a 5 segundos.,-5,0,100.0,100.0
DeltaChange1s,BURST_INTENSITY,burst_events,delta_t-delta_t-1,contracts,Salto instantáneo de agresión.,-2,0,100.0,100.0
DeltaChangeZScore,BURST_INTENSITY,burst_events,z(delta_change; history 300s),z,Rareza del cambio frente al pasado.,-300,0,100.0,100.0
DeltaPercentile,BURST_INTENSITY,burst_events,percentile(|delta_change|; history),ratio,Percentil causal de actividad.,-300,0,100.0,100.0
Delta_AtEntry,BURST_INTENSITY,trade_inputs,bar delta at prediction,contracts,Agresión acumulada disponible.,-60,0,100.0,100.0
Delta_Change_AtEntry,BURST_INTENSITY,trade_inputs,delta-current minus previous,contracts,Cambio de agresión al decidir.,-120,0,100.0,100.0
Dist_HVN_Ticks,BURST_INTENSITY,burst_events,(price-nearest_hvn)/tick,ticks,Distancia a nodo de alto volumen.,-1800,0,100.0,100.0
Dist_LVN_Ticks,BURST_INTENSITY,burst_events,(price-nearest_lvn)/tick,ticks,Distancia a nodo de bajo volumen.,-1800,0,100.0,100.0
Dist_VAH_Ticks,BURST_INTENSITY,burst_events,(price-vah)/tick,ticks,Ubicación respecto al VAH causal.,-1800,0,100.0,100.0
Dist_VAL_Ticks,BURST_INTENSITY,burst_events,(price-val)/tick,ticks,Ubicación respecto al VAL causal.,-1800,0,100.0,100.0
PeakNegativeDelta,BURST_INTENSITY,burst_events,"min(delta_1s, 10s)",contracts,Pico vendedor causal.,-10,0,100.0,100.0
PeakPositiveDelta,BURST_INTENSITY,burst_events,"max(delta_1s, 10s)",contracts,Pico comprador causal.,-10,0,100.0,100.0
PreBurst_Impulse_Decay_Slope_5s,BURST_INTENSITY,burst_events,OLS slope of directional one-second moves,ticks/s2,Decaimiento o expansión del impulso.,-5,0,100.0,100.0
PreBurst_Impulse_Survival_Seconds,BURST_INTENSITY,burst_events,consecutive directional seconds ending at burst,seconds,Supervivencia causal del impulso.,-5,0,100.0,100.0
PreBurst_Local_Entropy_10s,BURST_INTENSITY,burst_events,"binary entropy(up,down)",bits,Complejidad de la secuencia previa.,-10,0,100.0,100.0
PreBurst_Path_Efficiency_10s,BURST_INTENSITY,burst_events,directional net move/absolute path,ratio,Eficiencia de trayectoria previa.,-10,0,100.0,100.0
PreBurst_Rotation_Index_10s,BURST_INTENSITY,burst_events,direction changes/nonzero price changes,ratio,Rotación local de la subasta.,-10,0,100.0,100.0
PreEntry_Directional_Delta_Share3_AtEntry,BURST_INTENSITY,trade_inputs,execution_sign*sum delta/sum volume prior 3 closed bars,ratio,Persistencia de agresión previa.,-240,-1,100.0,100.0
PreEntry_Directional_Efficiency3_AtEntry,BURST_INTENSITY,trade_inputs,execution_sign*net move/sum ranges of prior 3 closed bars,ratio,Eficiencia de trayectoria previa.,-240,-1,100.0,100.0
PreEntry_Range_Compression3_AtEntry,BURST_INTENSITY,trade_inputs,"ATR3/max(OR range,1)",ratio,Compresión o expansión previa normalizada.,-240,-1,100.0,100.0
PreEntry_Volume_Climax_Ratio_AtEntry,BURST_INTENSITY,trade_inputs,last closed volume/mean earlier closed volumes,ratio,Clímax de participación antes del entry.,-300,-1,100.0,100.0
Previous_Delta_AtEntry,BURST_INTENSITY,trade_inputs,previous closed bar delta,contracts,Agresión previa cerrada.,-120,-1,100.0,100.0
Previous_Volume_AtEntry,BURST_INTENSITY,trade_inputs,previous closed bar volume,contracts,Actividad previa cerrada.,-120,-1,100.0,100.0
Realized_Volatility_10s_Ticks,BURST_INTENSITY,burst_events,sqrt(sum(one-second return_ticks^2)),ticks,Volatilidad realizada corta previa.,-10,0,100.0,100.0
Realized_Volatility_30s_Ticks,BURST_INTENSITY,burst_events,sqrt(sum(one-second return_ticks^2)),ticks,Volatilidad realizada media previa.,-30,0,100.0,100.0
Realized_Volatility_60s_Ticks,BURST_INTENSITY,burst_events,sqrt(sum(one-second return_ticks^2)),ticks,Régimen de volatilidad previo.,-60,0,100.0,100.0
Score_AtEntry,BURST_INTENSITY,trade_inputs,score available at prediction,points,Confluencia causal predefinida.,-60,0,100.0,100.0
Seconds_From_Open_AtEntry,BURST_INTENSITY,trade_inputs,entry_ny-09:30 NY,seconds,Régimen temporal exacto al decidir.,-600,0,100.0,100.0
Sell_Imbalance_Count_AtEntry,BURST_INTENSITY,trade_inputs,sell imbalance count,count,Desequilibrios vendedores observados.,-60,0,100.0,100.0
Short_Long_Volatility_Ratio,BURST_INTENSITY,burst_events,RV10/sqrt(10) divided by RV60/sqrt(60),ratio,Expansión o compresión de volatilidad antes del burst.,-60,0,100.0,100.0
Signed_Delta_Share_AtEntry,BURST_INTENSITY,trade_inputs,"execution_sign*bar delta/max(bar volume,1)",ratio,Agresión del bar alineada con la ejecución.,-60,0,100.0,100.0
Signed_Previous_Delta_Share_AtEntry,BURST_INTENSITY,trade_inputs,"execution_sign*previous delta/max(previous volume,1)",ratio,Agresión cerrada previa alineada.,-120,-1,100.0,100.0
TicksPerSecond,BURST_INTENSITY,burst_events,Velocity1s,ticks/s,Impacto observado en precio.,-1,0,100.0,100.0
TradesPerSecond,BURST_INTENSITY,burst_events,"count(trades,1s)",trades/s,Intensidad de ejecuciones.,-1,0,100.0,100.0
Velocity1s,BURST_INTENSITY,burst_events,price displacement/tick/1s,ticks/s,Desplazamiento de precio por segundo.,-1,0,100.0,100.0
Velocity3s,BURST_INTENSITY,burst_events,price displacement/tick/3s,ticks/s,Velocidad a 3 segundos.,-3,0,100.0,100.0
Velocity5s,BURST_INTENSITY,burst_events,price displacement/tick/5s,ticks/s,Velocidad a 5 segundos.,-5,0,100.0,100.0
Volume_AtEntry,BURST_INTENSITY,trade_inputs,bar volume at prediction,contracts,Participación acumulada disponible.,-60,0,100.0,100.0
absorption_pressure_1s,BURST_INTENSITY,engineered,"abs(Delta1s)/max(abs(Velocity1s),0.25)",contracts/tick,Agresión que no logra desplazar precio.,-1,0,100.0,100.0
acceleration_velocity_ratio,BURST_INTENSITY,engineered,"signed_acceleration/max(abs(signed_velocity),0.25)",ratio,Cambio relativo del impacto.,-2,0,100.0,100.0
burst_efficiency_score,BURST_INTENSITY,engineered,"signed_velocity_1s/max(abs(signed_delta_1s),1)",ticks/contract,Eficiencia direccional: breakout limpio alto.,-1,0,100.0,100.0
delta_persistence_1_3,BURST_INTENSITY,engineered,"abs(Delta3s)/(3*max(abs(Delta1s),1))",ratio,Persistencia normalizada de agresión.,-3,0,100.0,100.0
delta_persistence_3_5,BURST_INTENSITY,engineered,"3*abs(Delta5s)/(5*max(abs(Delta3s),1))",ratio,Persistencia de 3 a 5 segundos.,-5,0,100.0,100.0
delta_share_of_volume,BURST_INTENSITY,engineered,"abs(Delta1s)/max(ContractsPerSecond,1)",ratio,Fracción direccional del volumen.,-1,0,100.0,100.0
liquidity_absorption_score,BURST_INTENSITY,engineered,"absorption_pressure_1s*(1-min(abs(signed_velocity_1s)/10,1))",index,Presión alta con bajo desplazamiento.,-1,0,100.0,100.0
mean_trade_size,BURST_INTENSITY,engineered,"ContractsPerSecond/max(TradesPerSecond,1)",contracts/trade,Tamaño medio de ejecución.,-1,0,100.0,100.0
price_impact_per_100_contracts,BURST_INTENSITY,engineered,"100*abs(Velocity1s)/max(ContractsPerSecond,1)",ticks/100 contracts,Eficiencia de impacto del flujo.,-1,0,100.0,100.0
range,BURST_INTENSITY,trade_inputs,OR range at prediction,ticks,Régimen de apertura al decidir.,0,0,100.0,100.0
signed_acceleration_1s,BURST_INTENSITY,engineered,burst_sign*Acceleration1s,ticks/s2,Aceleración dirigida del precio.,-2,0,100.0,100.0
signed_delta_1s,BURST_INTENSITY,engineered,burst_sign*Delta1s,contracts,Agresión en dirección del burst.,-1,0,100.0,100.0
signed_delta_change_1s,BURST_INTENSITY,engineered,burst_sign*DeltaChange1s,contracts,Aceleración de agresión dirigida.,-2,0,100.0,100.0
signed_velocity_1s,BURST_INTENSITY,engineered,burst_sign*Velocity1s,ticks/s,Velocidad en dirección del burst.,-1,0,100.0,100.0
signed_velocity_3s,BURST_INTENSITY,engineered,burst_sign*Velocity3s,ticks/s,Persistencia de velocidad dirigida.,-3,0,100.0,100.0
Pre_Approach_Distance_Ticks,CROSSING_ANATOMY,burst_events,side_sign*(level-price_start_5s)/tick,ticks,Distancia recorrida antes del cruce.,-5,0,100.0,100.0
Pre_Approach_Pause_Seconds,CROSSING_ANATOMY,burst_events,count one-second buckets with movement <1 tick,seconds,Pausa o compresión inmediatamente antes del cruce.,-5,0,100.0,100.0
Pre_Approach_Velocity_TPS,CROSSING_ANATOMY,burst_events,directional displacement/observed seconds,ticks/s,Velocidad de aproximación al nivel.,-5,0,100.0,100.0
PreBurst_Price_Per_Delta_3s,EFFORT_RESULT,burst_events,directional ticks/abs(delta),ticks/contract,Resultado de precio por agresión.,-3,0,100.0,100.0
PreBurst_Price_Per_Volume_3s,EFFORT_RESULT,burst_events,directional ticks/volume,ticks/contract,Resultado de precio por volumen.,-3,0,100.0,100.0
Delta_Retention_1_3,FLOW_PERSISTENCE,burst_events,"delta[1,3]/abs(delta[0,1])",ratio,Persistencia de agresión sin solapamiento.,-3,0,100.0,100.0
Delta_Retention_3_5,FLOW_PERSISTENCE,burst_events,"delta[3,5]/abs(delta[1,3])",ratio,Extinción previa de agresión.,-5,-1,97.14285714285714,97.77777777777777
Flow_0_1_CounterflowShare,FLOW_PERSISTENCE,burst_events,"contra_volume/gross_volume [0,1]s",ratio,Conflicto agresivo oculto por el delta neto.,-1,0,100.0,100.0
Flow_0_1_DirectionalNetDelta,FLOW_PERSISTENCE,burst_events,"side_sign*(buy-sell), segment [0,1]s",contracts,Agresión neta inmediata sin ventanas superpuestas.,-1,0,100.0,100.0
Flow_0_1_DirectionalVelocityTPS,FLOW_PERSISTENCE,burst_events,"directional ticks/[0,1]s",ticks/s,Resultado de precio inmediato.,-1,0,100.0,100.0
Flow_0_1_GrossAggressive,FLOW_PERSISTENCE,burst_events,"raw_buy+raw_sell [0,1]s",contracts,Esfuerzo agresivo bruto inmediato.,-1,0,100.0,100.0
Flow_0_1_TicksPerAggressiveContract,FLOW_PERSISTENCE,burst_events,directional_ticks/gross_aggressive,ticks/contract,Esfuerzo versus resultado con denominador auditable.,-1,0,100.0,100.0
Flow_1_3_CounterflowShare,FLOW_PERSISTENCE,burst_events,"contra_volume/gross_volume [1,3]s",ratio,Contra-agresión previa al burst.,-3,-1,100.0,100.0
Flow_1_3_DirectionalNetDelta,FLOW_PERSISTENCE,burst_events,"side_sign*(buy-sell), segment [1,3]s",contracts,Persistencia previa independiente del segundo del burst.,-3,-1,100.0,100.0
Flow_1_3_DirectionalVelocityTPS,FLOW_PERSISTENCE,burst_events,"directional ticks/2s [1,3]",ticks/s,Persistencia de desplazamiento no superpuesta.,-3,-1,100.0,100.0
Flow_1_3_GrossAggressive,FLOW_PERSISTENCE,burst_events,"raw_buy+raw_sell [1,3]s",contracts,Esfuerzo bruto previo independiente.,-3,-1,100.0,100.0
Flow_3_5_CounterflowShare,FLOW_PERSISTENCE,burst_events,"contra_volume/gross_volume [3,5]s",ratio,Contra-agresión del contexto inmediato.,-5,-3,100.0,100.0
Flow_3_5_DirectionalNetDelta,FLOW_PERSISTENCE,burst_events,"side_sign*(buy-sell), segment [3,5]s",contracts,Régimen de flujo anterior no superpuesto.,-5,-3,100.0,100.0
Flow_3_5_DirectionalVelocityTPS,FLOW_PERSISTENCE,burst_events,"directional ticks/2s [3,5]",ticks/s,Desplazamiento anterior independiente.,-5,-3,100.0,100.0
Flow_3_5_GrossAggressive,FLOW_PERSISTENCE,burst_events,"raw_buy+raw_sell [3,5]s",contracts,Esfuerzo bruto de contexto.,-5,-3,100.0,100.0
Flow_Aligned_Segment_Count,FLOW_PERSISTENCE,burst_events,count non-overlap segments with directional delta and price >0,count,Alineación multihorizonte del esfuerzo y resultado.,-5,0,100.0,100.0
Flow_Conflict_Segment_Count,FLOW_PERSISTENCE,burst_events,count segments where delta and price have opposite signs,count,Conflicto multihorizonte compatible con absorción.,-5,0,100.0,100.0
Velocity_Retention_1_3,FLOW_PERSISTENCE,burst_events,"velocity[1,3]/abs(velocity[0,1])",ratio,Persistencia de velocidad sin solapamiento.,-3,0,97.14285714285714,95.55555555555556
Velocity_Retention_3_5,FLOW_PERSISTENCE,burst_events,"velocity[3,5]/abs(velocity[1,3])",ratio,Extinción o continuación del impulso.,-5,-1,80.0,88.88888888888889
Nearest_OR_Edge_Retest_Count_AtEntry,LEVEL_MEMORY,trade_inputs,closed bars touching nearest OR edge before entry,count,Desgaste causal del nivel por retests.,-600,-1,100.0,100.0
Prior_Full_Crosses_60s,LEVEL_MEMORY,burst_events,count complete side changes across frozen level,count,Chop frente a nivel fresco.,-60,0,100.0,100.0
Prior_Level_Touches_60s,LEVEL_MEMORY,burst_events,count(seconds touching fixed 1-tick level band),count,Memoria y desgaste del nivel antes del burst.,-60,0,100.0,100.0
Prior_Volume_At_Level_Band_60s,LEVEL_MEMORY,burst_events,sum volume in fixed 1-tick level band,contracts,Esfuerzo acumulado negociado en el nivel.,-60,0,100.0,100.0

