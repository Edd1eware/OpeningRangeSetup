# Micro-addendum V2-5 — fuente de `OR_ticks` (propuesta Claude, pendiente contrafirma Codex)

Fecha: 2026-07-25
Alcance: fija ÚNICAMENTE de dónde sale `OR_ticks` para los 98 eventos. No cambia
la definición del Opening Range, el endpoint, el score ni ningún gate.

## 1. Por qué hace falta

El endpoint congelado usa `OR_ticks` como normalizador:

```text
Y_60 = sigma * [(mH - m1)/delta_p] / max(OR_ticks, 1)
```

La *definición* del Opening Range ya está congelada en el proyecto
(`07_Eddieware_Opening_range_after_sync.py`: `OPENING_CANDLE_TIME = "09:30"`,
`TICK_SIZE = 0.25`) = vela de 1 minuto de las 09:30 ET. Lo que NO estaba
especificado es la *fuente de datos* de esa vela para estos 98 eventos.

## 2. Fuente propuesta: el MBO snapshot YA SELLADO

```text
archivo   = databento_mbo/liquidity_burst_snapshot_discovery100_20260723/
            NQ_MBO_SNAPSHOT_<fecha>_<BurstId>.mbo.dbn.zst
ventana   = trades (action == "T") con ts_event en [09:30:00, 09:31:00) hora
            America/New_York del mismo día
OR_high   = max(price) de esos trades
OR_low    = min(price) de esos trades
OR_ticks  = (OR_high - OR_low) / 0.25
```

Razones:

1. **Mismo proveedor y reloj** que el resto del estudio (Databento GLBX MBO). No
   mezcla footprints de ATAS/Rithmic ni `ohlcv` de otro producto.
2. **Ya sellado y pagado.** Cobertura verificada: `[cutoff-48 721 s, cutoff)`,
   contiene 09:30 con holgura. Cero descarga nueva.
3. **Causal.** La vela 09:30–09:31 cierra antes de `t0` (los cutoffs están en
   09:31–09:36 ET). `OR` queda íntegramente anterior a `t0`, como exige el
   preregistro.
4. **Determinista.** Sin interpolación ni forward-fill.

Verificación piloto (2022-04-05): 3 726 trades en el minuto, OR_high 15 129.50,
OR_low 15 095.75, `OR_ticks = 135`.

## 3. Faltantes

Si un evento no tiene ningún trade en `[09:30:00, 09:31:00)` NY, `OR_ticks` se
marca ausente con razón mecánica y el evento queda fuera del endpoint (cuenta
contra la cobertura mínima de 56). No se amplía la ventana, no se usa otra
sesión, no se sustituye por un OR de otra fuente.

## 4. Prohibiciones

No se cambia `OPENING_CANDLE_TIME`, ni el tick, ni se prueban ORs alternativos
(09:30–09:35, primeros N minutos, etc.). No se descarga nada. `OR_ticks` se
calcula y se sella ANTES de mirar cualquier `Y_60` o correlación.

Firma: Claude Fable. Contrafirma Codex: PENDIENTE.

`INFORMATION_STATUS=OR_SOURCE_PROPOSED_NO_OUTCOME`
