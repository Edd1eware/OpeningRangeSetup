# Protocolo de investigación — entrada retrasada 5 s para Liquidity Burst

Fecha de congelación: 2026-07-20 (America/Mexico_City)

Estado: PREREGISTRADO ANTES DE CALCULAR EL WR/PF REAL DE LA ENTRADA RETRASADA.

## Propósito de este documento

Este archivo conserva el contexto, las reglas y el siguiente trabajo de investigación para poder reanudarlo en otro chat sin reinterpretar el objetivo ni escoger reglas después de ver el resultado.

El objetivo final de todas las corridas es distinguir causalmente, dentro de una señal Liquidity Burst:

- absorción verdadera: la agresión no consigue continuidad y la operación de reversión tiene oportunidad;
- breakout limpio: la agresión consigue desplazamiento/aceptación y la operación de reversión debe evitarse.

La pregunta inmediata ya no es si ambas familias pueden etiquetarse después del trade. La pregunta es si una confirmación disponible aproximadamente cinco segundos después de publicarse el burst permite entrar a un precio todavía operable y mejorar WR/PF sin matar la frecuencia.

## Estado validado de la corrida histórica

- Replay: Historia X10 únicamente; Replay X1 deshabilitado.
- Fechas históricas consolidadas: 736 de 736 PASS.
- No es necesario repetir la corrida de aproximadamente 79 horas para esta primera investigación offline.
- Entradas Liquidity Burst causales: 184.
- Familia A, absorción verdadera estricta: 46.
- Familia B, breakout limpio estricto: 78.
- Familia C, trayectoria mixta: 60.
- Familia D: 0.
- Respuestas post-burst capturadas: horizontes de 1, 3 y 5 segundos.
- Filas en `burst_response_events.csv`: 1,611.
- Eventos de entrada con respuesta válida a 5 segundos: 180 de 184.
- Cuatro entradas no tienen respuesta completa a 5 segundos y deben quedar explícitamente como `NO_RESPONSE`, nunca imputadas.

Las cuatro fechas que originalmente aparecieron como `NON_TERMINAL_CSV` fueron falsos negativos causados por una carrera de lectura/escritura. Sus CSV raíz eran terminales y fueron recuperados. La comparación final quedó en 736 PASS y 0 FAIL.

El análisis de familias falló inicialmente por convertir un `NaN` legítimo a entero. Se corrigió con `_safe_int`; el análisis terminó y Telegram confirmó `telegram_sent=True`.

## Resultado científico disponible antes de esta fase

En el instante original de entrada (`t0`) no se encontró una feature que cumpliera simultáneamente:

- significancia corregida;
- tamaño de efecto suficiente;
- dirección estable en discovery, validation y holdout.

Por lo tanto, los datos causales disponibles en `t0` no justifican todavía un filtro inmediato.

Los modelos de `t0` se degradaron en holdout. Ejemplos:

- random forest: balanced accuracy 0.640 en validation y 0.383 en holdout;
- logistic: 0.544 en validation y 0.292 en holdout;
- CatBoost: 0.548 en validation y 0.403 en holdout.

Esto prohíbe presentar los resultados originales de esos modelos como una solución operativa.

## Hallazgo exploratorio que motiva esta investigación

Las variables post-burst no son válidas para predecir la entrada original porque `AvailableBeforeEntry=0` y `Model_Eligibility=POST_BURST_ONLY`. Sí pueden ser causales para una estrategia nueva que espere la ventana completa antes de decidir.

La señal individual más clara fue `Directional_Displacement_Ticks` a cinco segundos.

Regla exploratoria estricta encontrada usando discovery:

> Clasificar como absorción cuando `Directional_Displacement_Ticks <= -1`; clasificar como breakout probable en caso contrario.

La notación anterior equivale al umbral numérico exploratorio `<= -0.5` porque los desplazamientos observados son enteros.

Resultados clasificatorios sin reajustar el umbral:

| Split | Breakouts detectados | Absorciones conservadas | Balanced accuracy |
| --- | ---: | ---: | ---: |
| Validation | 13/16 = 81.2% | 7/8 = 87.5% | 84.4% |
| Holdout | 15/19 = 78.9% | 9/9 = 100.0% | 89.5% |

Advertencias:

- Este holdout ya fue abierto; cualquier confirmación definitiva necesita fechas nuevas.
- La familia original usa el desenlace del trade original. La buena clasificación no demuestra rentabilidad de una entrada retrasada.
- Parte del movimiento favorable puede haber ocurrido antes de `t+5s`.
- No se permite reutilizar el precio ni el resultado de la entrada original para afirmar WR/PF de la entrada retrasada.

## Frecuencia observada de las políticas candidatas

### Política estricta

Condición: operar sólo si el desplazamiento a 5 s es `<= -1 tick`.

- 82 de 184 entradas conservadas: 44.6%.
- Promedio: 2.16 entradas por mes activo.
- Mediana: 2 entradas por mes.
- Seis de 38 meses activos quedarían sin entradas.
- Absorciones A conservadas: 34/46 = 73.9%.
- Breakouts B admitidos: 16/78 = 20.5%.
- Trayectorias C conservadas: 32/60 = 53.3%.

Esta política puede matar demasiada operativa y no será la política principal para evaluar continuidad de frecuencia.

### Política operativa de tres estados

Reglas congeladas para la siguiente prueba:

1. `CONFIRMED_ABSORPTION`: desplazamiento `<= -1 tick`.
2. `AMBIGUOUS`: desplazamiento de `0` o `+1 tick`.
3. `PROBABLE_BREAKOUT`: desplazamiento `>= +2 ticks`.
4. `NO_RESPONSE`: sin respuesta causal completa a cinco segundos.

Conteos históricos:

- Confirmed absorption: 82.
- Ambiguous: 40.
- Confirmed absorption + ambiguous: 122 de 184 = 66.3%.
- Probable breakout: 58.
- No response: 4.
- Frecuencia de los primeros dos estados combinados: 3.21 entradas por mes activo.
- Mediana: 3 entradas por mes.
- Sólo un mes activo quedaría sin entradas.
- Absorciones A conservadas: aproximadamente 87%.
- Breakouts B todavía admitidos: aproximadamente 51.3%.

La zona ambigua no queda autorizada automáticamente para tamaño completo. Se debe reportar por separado y comparar estas alternativas sin ocultarlas:

- A: operar únicamente `CONFIRMED_ABSORPTION`;
- B: operar `CONFIRMED_ABSORPTION` y `AMBIGUOUS` con tamaño completo;
- C: tamaño completo en `CONFIRMED_ABSORPTION` y tamaño reducido preregistrado en `AMBIGUOUS` sólo después de conocer A y B. La alternativa C será exploratoria, no confirmatoria.

## WR/PF conocidos y lo que todavía se desconoce

El WR/PF real de la entrada retrasada aún no se conoce.

Las siguientes cifras reutilizan el precio y outcome del trade original; son referencias exploratorias y no resultados válidos de la política retrasada:

| Política | Trades | Frecuencia/mes activo | WR original | PF original | Expectancy original |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sin filtro | 184 | 4.84 | 52.17% | 0.909 | -2.61 ticks/trade |
| Estricta `<= -1` | 82 | 2.16 | 74.39% | 2.452 | +22.32 ticks/trade |
| Operativa `<= +1` | 122 | 3.21 | 61.48% | 1.330 | +7.62 ticks/trade |

Para la política operativa, el holdout cronológico reutilizando outcomes originales quedó en WR 52.2%, PF 1.00 y neto 0. En 2025 quedó en -210 ticks. Esto muestra inestabilidad y obliga a reconstruir el trade desde el nuevo instante.

## Hipótesis preregistradas

### Hipótesis principal H1

Una decisión tomada sólo cuando la respuesta de cinco segundos está completamente disponible puede reducir los breakouts perdedores y conservar suficiente frecuencia, incluso después de recalcular entrada, TP y SL desde el precio retrasado.

### Hipótesis nula H0

La aparente separación se explica porque la reversión ya comenzó durante los cinco segundos; al mover la entrada, la ventaja desaparece por precio peor, objetivos perdidos o inestabilidad temporal.

### Política primaria para frecuencia

La política primaria será operar `CONFIRMED_ABSORPTION + AMBIGUOUS`, equivalente a `Directional_Displacement_Ticks <= +1`, porque mantiene aproximadamente tres entradas por mes activo.

### Política secundaria

La regla estricta `<= -1` se reportará como comparación de pureza frente a frecuencia, no como selección posterior basada en PF.

## Simulación causal requerida

Para cada BurstId elegible:

1. Usar `Response_Available_Timestamp_UTC` del horizonte de cinco segundos como instante mínimo de decisión.
2. Prohibir cualquier precio anterior a ese timestamp.
3. Definir el precio de entrada como el primer precio ejecutable observado en o después del timestamp de decisión.
4. Mantener el lado original de ejecución, opuesto al burst.
5. Aplicar TP/SL desde el nuevo precio de entrada usando el plan inicial canónico de cada trade.
6. Recorrer cronológicamente la trayectoria posterior y registrar cuál barrera se toca primero.
7. Si TP y SL aparecen dentro de una misma observación sin orden intrabar demostrable, marcar `AMBIGUOUS_SAME_OBSERVATION`; no asumir TP.
8. Recalcular desde cero:
   - resultado TP/SL/BE/TIME_OVER;
   - ticks netos;
   - MAE y MFE;
   - duración;
   - precio perdido o mejorado respecto a la entrada original;
   - señal que alcanzó TP/SL antes de estar disponible la confirmación;
   - entradas por mes.
9. No reutilizar `Result_Label`, `result TP SL BE`, `MAE_ticks` o `MFE_ticks` originales como outcome retrasado.
10. Conservar un ledger por trade con origen exacto de cada timestamp y precio.

## Auditoría de disponibilidad de datos

Fuentes ya confirmadas:

- `burst_response_events.csv` contiene precio y métricas a 1, 3 y 5 segundos.
- `absorption_vs_breakout.csv` contiene BurstId, lado, entrada original, TP/SL iniciales y familia científica.
- Los CSV terminales por fecha son outcomes canónicos de la entrada original.
- Hay archivos `dynamic_timeline_*`, pero normalmente registran entrada y salida, no necesariamente cada tick entre ambos.
- Existe `data_footprint_generator/book_recordings/mbp_<fecha>_NY.csv`; antes de usarlo debe verificarse que contenga timestamps y precios ejecutables suficientes, cobertura para los 184 eventos y orden temporal determinista.

Si los archivos existentes no permiten determinar de manera inequívoca qué TP/SL retrasado se toca primero, el estudio offline debe terminar con estado `INSUFFICIENT_PATH_DATA`. No se fabricará una trayectoria ni se aproximará con el outcome original.

## Métricas obligatorias

Se reportarán para baseline, política estricta y política operativa:

- trades totales y por mes;
- WR incluyendo y excluyendo BE;
- PF;
- expectancy;
- gross profit y gross loss;
- average win y average loss;
- net ticks;
- MAE/MFE promedio y máximo;
- trades perdidos antes de confirmar;
- deterioro/mejora de entrada en ticks;
- resultados por año, mes, lado y split cronológico;
- drawdown secuencial en ticks;
- cobertura y causas de exclusión.

## Criterios de decisión congelados

La política operativa no avanza a implementación en ATAS salvo que:

1. tenga al menos 3.0 entradas por mes activo en la muestra evaluable;
2. conserve al menos 65% de la actividad original;
3. tenga PF global retrasado >= 1.20;
4. tenga expectancy retrasada > 0;
5. no dependa exclusivamente de un año;
6. validation y el periodo cronológico más reciente no muestren PF materialmente menor que 1.0;
7. la proporción de casos ambiguos por orden intrabar o falta de trayectoria sea suficientemente baja para no explicar el resultado;
8. no use ninguna variable disponible después de la nueva entrada.

El WR no se fija como umbral aislado porque TP y SL pueden ser dinámicos. Se reportará junto con average win/loss y PF.

Si la política operativa falla, no se optimizarán retrospectivamente docenas de umbrales. El camino siguiente será evaluar si Level 2/MBP ofrece reposición, consumo y retirada de liquidez causales para decidir en `t0`.

## Separación temporal y validez

- Splits existentes: 60% discovery, 20% validation y 20% holdout.
- El holdout existente ya fue observado durante la exploración de cinco segundos.
- Por eso esta fase se considera investigación retrospectiva y generación de hipótesis.
- Si el resultado offline es prometedor, la confirmación final exige fechas nuevas o una corrida futura con reglas totalmente congeladas.
- Ningún threshold se ajustará usando PF del holdout existente.

## Artefactos que debe producir la investigación

Crear una carpeta versionada bajo `outputs/`, por ejemplo:

`outputs/delayed_entry_5s_research_<timestamp>/`

Contenido mínimo:

- `run_manifest.json`
- `data_coverage_audit.csv`
- `delayed_trade_ledger.csv`
- `policy_summary.csv`
- `monthly_frequency.csv`
- `annual_stability.csv`
- `split_stability.csv`
- `exclusion_reasons.csv`
- `final_report.md`
- gráficas de equity, WR/PF por periodo, frecuencia mensual y deterioro de entrada.

El reporte debe distinguir explícitamente:

- `ORIGINAL_ENTRY_REFERENCE`;
- `DELAYED_ENTRY_RECONSTRUCTED`;
- `UNRESOLVED_PATH`.

## Archivos de entrada actuales

- Proyecto:
  `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup`
- Resultados históricos:
  `C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score`
- Dataset de familias:
  `outputs\absorption_breakout_research_20260720_085139\absorption_vs_breakout.csv`
- Respuestas post-burst:
  `C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\burst_response_events.csv`
- Informe previo:
  `contexto_features_atas\ANALISIS_FAMILIAS_ABSORCION_BREAKOUT_20260720_085139.md`
- Book recordings a auditar:
  `C:\Users\k_99_\Desktop\codding\data_footprint_generator\book_recordings`

## Estado de reanudación

Al momento de crear este documento:

1. El protocolo quedó documentado antes de calcular el WR/PF retrasado real.
2. La auditoría técnica de las trayectorias existentes está iniciada.
3. Todavía no se ha declarado que los MBP permitan simular fills o el orden TP/SL.
4. No se ha modificado la lógica de trading de ATAS.
5. No se ha iniciado una nueva corrida de Replay.
6. El siguiente paso exacto es auditar el esquema, timestamps, cobertura y granularidad de `book_recordings/mbp_<fecha>_NY.csv` contra los 184 BurstId.

## Instrucción para otro chat

Leer primero este archivo y después:

1. verificar la cobertura causal de MBP/price path;
2. implementar un simulador offline separado de la estrategia;
3. ejecutar las dos políticas congeladas;
4. publicar WR/PF sólo para operaciones reconstruidas desde `Response_Available_Timestamp_UTC`;
5. detenerse con `INSUFFICIENT_PATH_DATA` si el orden de precios no puede probarse;
6. no abrir ATAS ni lanzar otra corrida larga hasta terminar esta auditoría offline.

## Pivote autorizado durante la investigación

Decisión del usuario posterior a la preregistración: la solución principal no debe depender de esperar cinco segundos, porque eso reduce demasiado la frecuencia y permite que parte del movimiento ocurra antes de entrar. La investigación de `t+5s` queda relegada a control negativo y etiqueta científica.

Nuevo objetivo prioritario:

> Diferenciar absorción y breakout limpio mediante features causales disponibles antes de la entrada original, sin esperar la respuesta posterior del precio.

Reglas de este pivote:

1. `Directional_Displacement_Ticks`, `Response_MFE_Ticks`, `Response_MAE_Ticks`, `Acceptance_Dwell_Ratio` y cualquier columna de `burst_response_events.csv` calculada después del burst sólo pueden utilizarse como etiquetas o auditoría; nunca como predictor de la entrada original.
2. El cutoff máximo de cada feature será `prediction_timestamp` del dataset de familias. Toda observación con timestamp posterior se rechazará como leakage.
3. Se reutilizarán primero las grabaciones existentes; no se lanzará ATAS hasta saber si tienen cobertura y calidad suficientes.
4. La prioridad será obtener información pasiva que las 142 features de flujo/precio no contenían:
   - reposición agregada en el nivel atacado;
   - consumo ejecutado frente a cambio de profundidad;
   - velocidad de refill;
   - persistencia de profundidad después de varias agresiones;
   - pulling/stacking direccional;
   - OFI basado en cambios MBP;
   - resiliencia del nivel;
   - profundidad retirada por cada contrato ejecutado;
   - repetición de tests y supervivencia del nivel antes del publish.
5. Como no hay MBO por identidad de orden, cualquier métrica de refill será `MBP_APPROX` y no se describirá como iceberg confirmado.
6. Si el MBP no permite reconstruir cambios coherentes alrededor del nivel atacado, se documentará `MBP_INSUFFICIENT`; no se fabricarán features con ceros.
7. La evaluación seguirá discovery/validation/holdout cronológico. El holdout ya abierto sólo sirve para auditoría exploratoria; la confirmación final requerirá fechas nuevas.
8. Ninguna feature se convertirá en filtro hasta demostrar información incremental sobre el baseline, estabilidad temporal y mejora económica fuera de muestra.

Siguiente paso exacto después de este pivote:

1. medir cobertura MBP+tape en los 184 BurstId antes de `prediction_timestamp`;
2. verificar presencia y actualizaciones del `Broken_Level`/`Burst_Price` en ventanas de 1, 3, 5 y 10 segundos;
3. construir un ledger causal por evento con razones de ausencia;
4. sólo si la cobertura es suficiente, implementar las features MBP pre-entry y compararlas contra A/B sin usar respuesta futura.

## Resultado del pivote MBP+tape pre-entry

La auditoría y el análisis offline se completaron con cutoff estricto en `prediction_timestamp`:

- 184/184 timestamps causales válidos.
- MBP antes del cutoff: 172/184.
- Tape antes del cutoff: 174/184.
- Features MBP robustas bajo los criterios congelados: 0.
- MBP-only logistic holdout: ROC AUC 0.461.
- MBP-only random forest holdout: ROC AUC 0.511.
- Baseline+MBP no mejoró al baseline y permaneció inestable.
- Ninguna variable post-burst se utilizó como predictor.

Conclusión: el MBP agregado y el tape ya disponibles no permiten diferenciar A/B antes de la entrada. No se autoriza ningún filtro.

Artefactos válidos:

`outputs\preentry_liquidity_features_20260720_preentry_r2`

La carpeta `preentry_r1` queda invalidada porque inicialmente confundía ausencia de nivel con valor cero. R2 corrige esa ausencia como `NaN` y es la única versión válida.

## Hipótesis MBO y Databento

MBO no se presume rentable. Se justifica únicamente como último experimento de información pasiva ortogonal:

- MBP agrega volumen por precio y pierde identidad de órdenes.
- MBO conserva `order_id`, secuencia y acciones Add/Cancel/Modify/Trade/Fill.
- Esto permite medir reposición real aproximada por identidad, persistencia, concentración de makers, repeated fills, cancel-to-fill y barridos multi-nivel.
- Databento CME MBO no debe asumirse que expone prioridad explícita de cola; sólo se usarán campos realmente presentes.

Se preparó un manifiesto no facturable de ventanas causales:

`contexto_features_atas\DATABENTO_MBO_VENTANAS_CAUSALES_LIQUIDITY_BURST_20260720.csv`

Características:

- dataset `GLBX.MDP3`;
- schema `mbo`;
- símbolo continuo `NQ.v.0`, salida a raw symbol;
- 184 BurstId y 184 fechas únicas;
- 10 segundos previos por evento y 1 ms de padding técnico;
- 1,840.184 segundos totales, equivalentes a 30.67 minutos no contiguos;
- filtro local obligatorio: `ts_event <= causal_cutoff_utc_inclusive`.

No se descargó información ni se incurrió costo. La consulta gratuita de metadata devolvió `403 auth_account_locked`; después de desbloquear la cuenta debe consultarse `metadata.get_cost` y revisar el importe antes de cualquier descarga.

El experimento MBO se detendrá si:

1. la cobertura de acciones/order_id alrededor del nivel es insuficiente;
2. ninguna feature pre-registrada muestra información incremental en validation;
3. la dirección cambia por periodo;
4. baseline+MBO no supera al baseline de forma consistente;
5. el costo estimado no justifica el piloto.
