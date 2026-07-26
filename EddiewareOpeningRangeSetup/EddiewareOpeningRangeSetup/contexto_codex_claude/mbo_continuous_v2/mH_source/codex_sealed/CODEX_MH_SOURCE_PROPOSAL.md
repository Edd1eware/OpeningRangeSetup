# V2-5 — Propuesta Codex independiente para la fuente de `mH`

Fecha: 2026-07-25  
Estado: propuesta sellable, outcome-blind  
Alcance: addendum exclusivo de fuente de datos para `mH`

## 0. Invariante y alcance del addendum

Este addendum preregistra únicamente la fuente que falta para `mH`. No modifica
la definición congelada del endpoint:

```text
t1 = cutoff + 5.000 s
H = 60.000 s
tH = t1 + H = cutoff + 65.000 s

Y_60 = sigma * [(mH - m1) / delta_p] / max(OR_ticks, 1)
endpoint = rho_Spearman(S_defensa_aceptacion, Y_60)
```

La autorización acotada del usuario reemplaza solamente, para `mH`, la
restricción anterior de derivarlo de datos ya sellados. Fórmula, horizonte,
score, universo de 98 eventos, escalas, gates, bootstrap, umbral de éxito y
demás reglas del preregistro convergente permanecen intactos. Esta propuesta se
formuló sin abrir outcomes, mapping ni `admin_sealed`, y sin optimizar ninguna
decisión contra el resultado.

## 1. Producto y schema Databento

La única descarga autorizada será mediante Databento Historical API con:

```text
dataset = "GLBX.MDP3"
schema = "mbp-1"
```

Es decir, top-of-book MBP-1 del mismo feed CME Globex MDP 3.0. Se conservará la
respuesta original en DBN para poder hashearla y auditarla. No se solicitarán
`mbo`, `mbp-10`, `ohlcv-*`, trades de otro producto ni datos de otro proveedor.

## 2. Símbolo y `stype`

Para cada uno de los 98 eventos se consultará literalmente su contrato raw ya
congelado antes de outcomes:

```text
symbols = [resolved_raw_symbol_del_evento]
stype_in = "raw_symbol"
```

No se usará un símbolo continuo (`NQ.c.0`, `NQ.v.0` o equivalente), no se hará
una nueva selección de vencimiento y no se remapeará el contrato después de
observar datos futuros. El símbolo enviado debe ser exactamente el
`resolved_raw_symbol` que ya quedó asociado a ese evento y que se usó para la
cotización acotada.

## 3. Ventana temporal mínima por evento

Definido `tH = cutoff + 65.000 s`, cada petición tendrá, en UTC y con `end`
exclusivo:

```text
start = cutoff + 64.000 s     (inclusivo)
end   = cutoff + 65.050 s     (exclusivo)
```

Por tanto, la ventana es exactamente:

```text
[cutoff + 64.000 s, cutoff + 65.050 s)
```

Los 50 ms posteriores a `tH` son solo margen de adquisición para no depender de
la semántica exclusiva del límite derecho. Después de descargar, esos registros
se conservan para auditoría pero se excluyen del cálculo: ningún registro con
`ts_recv > tH` puede determinar `mH`. No se ampliará la ventana hacia atrás ni
hacia delante para rescatar faltantes.

La cotización ya medida para estas 98 peticiones, con esos parámetros, es
USD 4.173532 total y USD 0.0758 máximo por evento.

## 4. Cálculo determinista de `mH`

El reloj normativo es `ts_recv`, el mismo reloj usado para expresar la cobertura
relativa al `cutoff`. Para cada evento:

1. Se consideran solamente registros MBP-1 del contrato raw del evento con
   `ts_recv <= tH`.
2. Un BBO es completo cuando `bid_px_00` y `ask_px_00` son precios Databento
   válidos y no nulos/sentinel, y `ask_px_00 >= bid_px_00`. Tamaños, precio de
   trade u otros campos no sustituyen un lado ausente.
3. Se elige el último BBO completo en orden nativo DBN por `ts_recv`; si hay
   empate temporal, se respeta el orden de secuencia del feed y, como desempate
   final, el orden físico del registro en el DBN.
4. Sea `ts_BBO` el `ts_recv` del registro elegido. Solo es válido si:

```text
0 <= tH - ts_BBO <= 1.000 s
```

5. El midpoint se calcula exactamente a partir de ese BBO:

```text
mH = (bid_px_00 + ask_px_00) / 2
```

El cálculo se hará con la representación entera/fixed-price de Databento antes
de convertir unidades, para evitar error binario de coma flotante. Se admiten
midpoints de medio tick. No se usa el primer BBO posterior a `tH`, interpolación,
trade price, OHLCV, forward-fill de más de 1 segundo ni un proveedor alternativo.

## 5. Fuente de `m1`

`m1` no se redescarga. Se toma del MBO ya sellado, aplicando exactamente la regla
congelada:

```text
m1 = midpoint del último BBO completo anterior a t1
t1 = cutoff + 5.000 s
```

La descarga MBP-1 nueva no recalcula, valida, reemplaza ni selecciona entre
versiones de `m1`. Su único valor analítico es obtener `mH`.

## 6. Faltantes y cobertura

`mH` se marca ausente si no existe un BBO completo con `ts_recv <= tH` dentro de
la antigüedad máxima inclusiva de 1.000 segundo, si el contrato esperado no
resuelve, si la respuesta está vacía/corrupta o si no puede verificarse que el
registro pertenece al contrato raw congelado. Cada exclusión se reportará con
una razón mecánica y sin inspeccionar el signo o magnitud de `Y_60`.

Un evento tiene `Y_60` válido solo si también existen el `m1`, `delta_p`,
`OR_ticks` y `sigma` ya preregistrados. El endpoint incluye todos los eventos con
score evaluable y `Y_60` válido, sin filtrar por banda neutra, cola, lado ni
resultado.

Se requieren al menos 56 eventos válidos. Si la cobertura combinada es menor que
56, discovery es FAIL por cobertura: no se extiende la ventana, no se descarga
un schema adicional, no se sustituye el horizonte y no se crea un endpoint
alternativo.

## 7. Confirmación final de no expansión

El horizonte sigue siendo exactamente `H = +60.000 s` medido desde
`t1 = cutoff + 5.000 s`; por ello `mH` sigue evaluándose exactamente en
`cutoff + 65.000 s`. No se prueban otros horizontes.

La única adquisición nueva autorizada son las 98 ventanas MBP-1
`[cutoff+64.000 s, cutoff+65.050 s)` del contrato raw congelado de cada evento.
No se descarga nada para `m1`, features, Opening Range, otros contratos, otras
fechas, otros schemas, otros proveedores ni otros endpoints. Los DBN descargados,
el manifiesto de peticiones y sus hashes deben sellarse antes de cualquier
apertura de outcomes.

`INFORMATION_STATUS=MH_SOURCE_PREREGISTERED_NO_OUTCOME`
