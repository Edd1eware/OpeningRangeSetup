# Contrafirma V2-5 — fuente de `OR_ticks`

Fecha: 2026-07-25  
Veredicto: **FIRMADO**

## 1. Evaluación

Se acepta `OR_SOURCE_MICRO_ADDENDUM.md`. La fuente propuesta satisface el
prerregistro:

1. **Causalidad:** la ventana fija de evento termina a las 09:31:00 ET y debe
   quedar íntegramente antes de `t0`. La guardia de recepción fijada abajo impide
   incorporar mensajes aún no observables en `t0`.
2. **Proveedor único:** `OR`, `m1` y el resto del snapshot previo proceden de
   Databento `GLBX.MDP3`; no se mezclan barras de ATAS/Rithmic ni OHLCV externo.
3. **Sin descarga nueva:** se usan exclusivamente los bytes del snapshot MBO ya
   sellado `liquidity_burst_snapshot_discovery100_20260723`.
4. **Determinismo:** ventana, reloj, contrato, filtro, límites y aritmética
   quedan fijados en este documento.
5. **Faltantes:** excluir el caso del endpoint es correcto. La cobertura de 56
   se aplica al número final de pares con score evaluable y `Y_60` completo, no
   a una cobertura separada de `OR`.

## 2. Especificación mecánica normativa

Para cada evento, sea `D` la fecha civil de `t0` en
`America/New_York` y:

```text
W = [D 09:30:00.000000000, D 09:31:00.000000000)
```

Se lee únicamente el archivo sellado del propio evento:

```text
databento_mbo/liquidity_burst_snapshot_discovery100_20260723/
NQ_MBO_SNAPSHOT_<fecha>_<BurstId>.mbo.dbn.zst
```

No se busca un archivo alternativo si éste falta y no se sustituye el contrato.
Sólo son elegibles los registros que cumplan simultáneamente:

```text
instrumento = contrato congelado del evento
action == "T"
ts_event >= inicio(W)
ts_event <  fin(W)
ts_recv < t0
price válido
```

`ts_event` es el reloj normativo para decidir a qué vela pertenece el trade.
`ts_recv` no redefine la vela: se usa exclusivamente como guardia
anti-lookahead. Antes de calcular se exige además `fin(W) <= t0`; si no se
cumple, el evento es inevaluable y la ventana no se desplaza.

Los límites locales se convierten una sola vez a instantes UTC con la zona IANA
`America/New_York` y se comparan con precisión de nanosegundos. No se usa un
offset UTC fijo: así EDT/EST queda resuelto mecánicamente por la fecha. El
inicio es inclusivo y el final exclusivo.

`price válido` significa precio fixed-point decodificado de Databento, no nulo,
no `NaN` y no el sentinel de precio indefinido. Un registro `T` con precio
inválido no participa y se contabiliza para auditoría. Los registros elegibles
deben estar sobre la cuadrícula congelada de `0.25`; una violación es un error
mecánico del evento, no una invitación a redondear.

El cálculo se hace en la representación entera/fixed-price de Databento:

```text
OR_high  = máximo precio elegible
OR_low   = mínimo precio elegible
OR_ticks = (OR_high - OR_low) / 0.25
```

No se convierte a `float` antes de la resta o división, no se redondea y no se
interpola. El resultado debe ser un entero no negativo. Un solo trade, o varios
al mismo precio, produce válidamente `OR_ticks = 0`; el denominador del endpoint
sigue siendo `max(OR_ticks, 1)`. El orden y los duplicados no alteran el
máximo/mínimo y no se introduce una regla de deduplicación.

## 3. Sesiones especiales y faltantes

No hay ajuste discrecional por feriados, apertura tardía, half-day ni otra
sesión especial. Siempre se intenta exactamente `W` en la fecha `D`. Si esa
sesión no contiene trades elegibles, no se mueve la ventana ni se toma otra
fecha, contrato, archivo, schema o proveedor.

Como mínimo se registran razones mecánicas distinguibles para:

```text
OR_SOURCE_FILE_MISSING
OR_SOURCE_DECODE_ERROR
OR_CONTRACT_MISMATCH
OR_WINDOW_NOT_PRE_T0
OR_NO_VALID_TRADE
OR_OFF_TICK_PRICE
```

Todo evento sin `OR_ticks` válido queda fuera del endpoint y reduce el conteo
final de pares válidos. Si quedan menos de 56, el resultado es
`FAIL_COVERAGE`; no se rescata ningún caso mediante sustitución o ampliación.

## 4. Test de regresión sellado

La implementación debe reproducir para `2022-04-05`, bajo las reglas anteriores:

```text
trades elegibles = 3,726
OR_high          = 15,129.50
OR_low           = 15,095.75
OR_ticks         = 135
```

Una discrepancia detiene la generación de `OR_ticks` para revisión mecánica; no
autoriza modificar ventana, filtro o fuente.

No se inspeccionó ningún `Y_60`, outcome, correlación, mapping ni
`admin_sealed` para emitir esta contrafirma.

Firma: Codex.

`INFORMATION_STATUS=OR_SOURCE_PREREGISTERED_NO_OUTCOME`
