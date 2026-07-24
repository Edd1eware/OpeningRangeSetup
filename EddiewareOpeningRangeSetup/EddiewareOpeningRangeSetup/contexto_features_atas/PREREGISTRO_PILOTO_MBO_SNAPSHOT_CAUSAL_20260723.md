# PREREGISTRO — PILOTO MBO CON SNAPSHOT CAUSAL

Fecha de congelación: 2026-07-23.  
Estado: **ETAPA TÉCNICA 6/6 DESCARGADA Y APROBADA; 18 SESIONES
ADICIONALES PENDIENTES DE AUTORIZACIÓN.**

## Objetivo único

Determinar si el estado completo del libro y su secuencia subsegundo, observados
exclusivamente antes de `t_decision`, aportan separación estable entre:

- A: absorción limpia;
- B: breakout limpio.

La familia C se conserva sin alteraciones, pero no se usa para entrenar ni
seleccionar el clasificador binario primario. Después de congelar el modelo A/B,
C sólo podrá utilizarse para estudiar una zona de abstención o baja confianza.

## Por qué se abre este piloto

El piloto MBO anterior quedó limitado por:

- 0 registros de snapshot;
- 21.88% de IDs censurados por la izquierda;
- posición y volumen iniciales de cola no reconstruibles;
- sincronización MBO–ATAS aproximada;
- 12 predictores MBO agregados que no normalizan consumo, cancelación y
  reposición por la liquidez realmente disponible.

Resultados que este preregistro no intentará reinterpretar:

- mejor baseline MATRIX: BA 0.550 y AUC 0.597, sin puerta discovery;
- MBO_CORE: BA 0.439 y AUC 0.451;
- MBO redujo BA y AUC en todos los bloques MATRIX comparables.

## Prohibiciones

- No usar 2025–2026 durante diseño, selección, normalización o ajuste.
- No usar MFE, MAE, TP, SL, PnL ni resultado del trade como predictor.
- No incorporar eventos cuyo orden causal frente a `t_decision` sea ambiguo.
- No buscar retrospectivamente nuevas ventanas, umbrales o combinaciones hasta
  encontrar una que funcione.
- No sustituir el modelo primario después de observar el resultado.
- No descargar las 24 sesiones antes de que las 6 técnicas pasen la puerta de
  integridad.
- No ampliar a más fechas si el piloto de señal no supera su puerta congelada.

## Fuente y reloj

Para cada sesión se solicitará:

```text
dataset    = GLBX.MDP3
schema     = mbo
symbol     = NQ.v.0
stype_in   = continuous
stype_out  = instrument_id
start      = 00:00:00 UTC
end        = inicio del milisegundo de t_decision, exclusivo
```

La descarga desde medianoche es necesaria para recibir el snapshot histórico
sintético y todos los incrementales posteriores. Databento no admite la
conversión directa `continuous -> raw_symbol` en la descarga. Antes de descargar
se resolverá `NQ.v.0 -> instrument_id -> raw_symbol`; el DBN se solicitará con
el contrato raw resuelto como entrada y `stype_out=instrument_id`. El manifiesto
y el recibo deben persistir ambos identificadores, además de `channel_id`,
`sequence`, `ts_event`, `ts_recv`, flags, acción, lado, precio, tamaño y
`order_id`.

El DOM, la cola y el tape de investigación se derivarán del mismo stream MBO.
ATAS sólo aportará `BurstId`, `t_burst`, `t_decision`, lado y niveles de
referencia.

### Regla de independencia del footprint

La similitud entre el footprint ATAS/Rithmic y el footprint derivado de
Databento **no es una puerta técnica ni científica**. Son feeds y procesos de
agregación distintos. No se exigirá igualdad de volumen por precio, delta,
bid/ask ni secuencia de trades.

- La reconciliación >=99% se calcula únicamente dentro del MBO: estado anterior
  más ADD/MODIFY/CANCEL/FILL frente al estado reconstruido.
- `L0:L2` se obtienen del BBO MBO inmediatamente anterior a `t_burst`, no del
  footprint de ATAS.
- El precio ATAS se reporta sólo como control descriptivo de alineación y no
  puede hacer fallar la puerta.
- Ninguna feature mezcla volúmenes de ATAS con denominadores de Databento.

### Regla causal estricta

El timestamp de la estrategia sólo tiene resolución de milisegundos. Por tanto:

1. se excluye por completo el milisegundo que contiene `t_decision`;
2. sólo se aceptan paquetes cuyo cierre `F_LAST` ocurre antes del cutoff
   exclusivo;
3. no se usa el orden de filas redondeadas para resolver empates;
4. ninguna feature puede leer estado posterior al cutoff.

## Selección congelada

Semilla:

```text
MBO_SNAPSHOT_PILOT_V1_20260723
```

El ranking dentro de cada celda se obtiene con:

```text
SHA256(semilla | BurstId)
```

Se excluyen feriados federales de Estados Unidos, Good Friday y sesiones CME
con horario festivo predefinidas. No se selecciona manualmente por resultado,
volatilidad, apariencia gráfica ni desempeño anterior.

### Etapa técnica: 6 sesiones

Una sesión por año y lado, alternando las familias para contener tres A y tres B:

| fecha | año | lado | familia | BurstId |
|---|---:|---|---|---|
| 2022-04-05 | 2022 | BUY | A_TRUE_ABSORPTION | LB_20220405_093200_BUY_0001 |
| 2022-08-31 | 2022 | SELL | B_CLEAN_BREAKOUT | LB_20220831_093400_SELL_0001 |
| 2023-05-18 | 2023 | BUY | B_CLEAN_BREAKOUT | LB_20230518_093436_BUY_0001 |
| 2023-08-29 | 2023 | SELL | A_TRUE_ABSORPTION | LB_20230829_093105_SELL_0001 |
| 2024-05-02 | 2024 | SELL | B_CLEAN_BREAKOUT | LB_20240502_093112_SELL_0001 |
| 2024-07-16 | 2024 | BUY | A_TRUE_ABSORPTION | LB_20240716_093212_BUY_0001 |

### Etapa de señal: 24 sesiones

Dos sesiones en cada una de las 12 celdas:

```text
3 años × 2 lados × 2 familias × 2 sesiones = 24
```

Son 24 fechas y 24 `BurstId` únicos. Las seis sesiones técnicas son subconjunto
de estas 24; por ello el costo de 24 ya incluye las seis.

## Puerta técnica obligatoria

Las seis sesiones deben cumplir simultáneamente:

| control | umbral |
|---|---:|
| snapshot presente | 6/6 |
| acción R con F_SNAPSHOT | 6/6 |
| acciones A con F_SNAPSHOT | 6/6 |
| cierre F_LAST del snapshot | 6/6 |
| stype_out instrument_id persistido | 6/6 |
| contrato raw resuelto y persistido por metadatos | 6/6 |
| F_MAYBE_BAD_BOOK | 0 |
| retrocesos de sequence incremental dentro de canal | 0 |
| estado del libro reconciliado internamente en MBO | >=99% |
| niveles atacados reconstruibles en t_burst | 6/6 |
| eventos usados después del cutoff | 0 |

La coincidencia con el footprint ATAS queda expresamente excluida de esta tabla.
Los registros sintéticos `F_SNAPSHOT` también se excluyen del control de
monotonicidad: conservan secuencias históricas y están ordenados por prioridad
de cola, no como incrementales del feed. Sí permanecen en la reconstrucción del
estado inicial.

Si falla cualquier punto no se completan las 24 y no se construyen features.

## Sistema de coordenadas

Todo se orientará respecto al movimiento esperado:

- Burst BUY: lado atacado = ASK;
- Burst SELL: lado atacado = BID.

`L0` es el mejor precio pasivo atacado inmediatamente antes de `t_burst`.
`L1` y `L2` son los dos precios siguientes en la dirección del Burst. El bloque
atacado es `L0:L2`. Todas las cantidades se normalizan por la profundidad
inicial del bloque o por una magnitud preburst causal; no se usan precios o
cantidades absolutas como señal primaria.

## Ocho features primarias congeladas

Las definiciones detalladas están en
`MBO_SNAPSHOT_PRIMARY_FEATURE_SPEC_20260723.csv`.

1. `consumption_initial_depth_ratio_250ms`
2. `withdrawal_initial_depth_ratio_250ms`
3. `durable_refill_removed_ratio_250ms`
4. `initial_queue_survival_ratio_250ms`
5. `impact_efficiency_250ms`
6. `depletion_persistence_share_500ms`
7. `absorption_motif_share_500ms`
8. `breakout_motif_share_500ms`

Ventanas cerradas antes de ver resultados:

```text
[0,50), [50,100), [100,250), [250,500) ms desde t_burst
```

Si `t_decision` llega antes, la ventana se trunca causalmente y se registra su
cobertura. Las métricas same-ID, new-ID, edad y cola se conservarán como
diagnóstico, pero no podrán entrar al modelo primario de ocho features.

## Modelos congelados

Primario:

```text
logistic_C_0.2_balanced
```

Comparaciones:

1. `MATRIX_TRANSITIONS`;
2. `MBO_SNAPSHOT_8`;
3. `MATRIX_TRANSITIONS_PLUS_MBO_SNAPSHOT_8`.

CatBoost queda prohibido en la muestra de 24. Sólo podrá ejecutarse como
diagnóstico secundario después de alcanzar al menos 60 A/B, sin reemplazar la
conclusión del modelo primario.

## Puerta del piloto de señal

La ampliación sólo se permite si el bloque combinado cumple todo:

| métrica | umbral |
|---|---:|
| balanced accuracy LOYO | >=0.58 |
| ROC AUC LOYO | >=0.62 |
| sensibilidad A | >=0.55 |
| especificidad B | >=0.55 |
| mejora BA o AUC frente a MATRIX_TRANSITIONS | >=0.03 |
| dirección coherente de mecanismos centrales | >=5/6 bloques año/lado |

Esta puerta sólo autoriza ampliar discovery; no autoriza declarar que ya se
separan A y B.

## Puerta discovery estricta

Al alcanzar al menos 60 A/B se conserva la puerta ya utilizada:

- BA >=0.65;
- AUC >=0.68;
- sensibilidad A >=0.60;
- especificidad B >=0.60;
- límite inferior bootstrap de BA >0.55;
- permutación dentro de año `p<=0.05`;
- BA mínima por año/lado >=0.55;
- mejora BA o AUC >=0.03 frente al mejor bloque simple.

2025–2026 sólo se abre una vez después de superar esta puerta.

## Costo estimado sin descarga

Consulta realizada mediante `metadata.get_cost`; no se ejecutó `get_range`.

| alcance | sesiones | costo estimado USD |
|---|---:|---:|
| puerta técnica | 6 | 1.433332 |
| piloto completo | 24 | 6.657057 |
| costo incremental después de las 6 | 18 adicionales | 5.223725 |

Rango por sesión dentro del piloto de 24: USD 0.160129–0.389987.  
Promedio: USD 0.277377.

Los costos son estimaciones del proveedor y deben volver a consultarse si cambia
el manifiesto o antes de una ampliación posterior.

## Secuencia autorizable

1. Autorizar únicamente USD 1.433332 estimados para las seis sesiones.
2. Descargar y auditar las seis.
3. Si pasan todos los controles técnicos, solicitar autorización separada para
   completar las 24 por aproximadamente USD 5.223725 adicionales.
4. Construir exclusivamente las ocho features congeladas.
5. Ejecutar la puerta de señal.
6. Detenerse o ampliar según el resultado, sin tocar 2025–2026.

## Resultado de la etapa técnica

Ejecutado el 2026-07-23:

- 6/6 sesiones descargadas;
- 12,759,652 eventos MBO;
- 256,314,607 bytes comprimidos;
- snapshot completo: 6/6;
- contrato raw e instrument ID: 6/6;
- `F_MAYBE_BAD_BOOK`: 0;
- retrocesos de secuencia incremental: 0;
- reconciliación interna mínima: 100.0000%;
- censura izquierda máxima: 0.0000%;
- niveles atacados reconstruibles: 6/6;
- cutoff causal: 6/6;
- comparación footprint ATAS–Databento usada como puerta: no.

Veredicto: **PASA LA PUERTA TÉCNICA**. La construcción de las ocho features está
autorizada científicamente cuando se complete el piloto de 24. Este resultado no
constituye evidencia de separación A/B.

## Ampliación autorizada y resultado discovery 100

El usuario autorizó ampliar directamente a 100 sesiones para disponer de una
muestra A/B con tamaño suficiente. La selección permaneció congelada y mantuvo
2025–2026 cerrado:

- 100 sesiones: A=29, B=41, C=30;
- muestra primaria A/B: n=70;
- años: 2022=34, 2023=37, 2024=29;
- lados: BUY=47, SELL=53;
- feriados CME/EE. UU. incluidos: 0;
- seis archivos reutilizados y 94 sesiones nuevas descargadas;
- costo estimado de las 100: USD 27.978455;
- costo incremental estimado de las 94 nuevas: USD 26.545123;
- 257,564,810 eventos;
- 5,142,244,260 bytes comprimidos;
- espacio libre al terminar: 99.35 GB.

Auditoría causal completada el 2026-07-23:

- gate técnico: 100/100 PASS;
- snapshot completo: 100/100;
- contrato raw e instrument ID: 100/100;
- `F_MAYBE_BAD_BOOK`: 0;
- retrocesos de secuencia incremental: 0;
- reconciliación interna mínima: 99.9991759%;
- censura izquierda máxima: 0.0012563%;
- niveles MBO L0:L2 atacados reconstruibles: 100/100;
- cutoff causal: 100/100;
- eventos posteriores al cutoff descargados/usados: 0/0;
- comparación footprint ATAS–Databento usada como puerta: no.

Veredicto de datos: **READY_FOR_PREREGISTERED_FEATURE_EXTRACTION**. Esto
demuestra que la muestra de 100 conserva el estado inicial y la identidad
necesarios para construir las ocho features. No demuestra todavía que las
features separen absorción de breakout limpio; esa conclusión exige ejecutar la
validación predictiva preregistrada sobre las 70 observaciones A/B.
