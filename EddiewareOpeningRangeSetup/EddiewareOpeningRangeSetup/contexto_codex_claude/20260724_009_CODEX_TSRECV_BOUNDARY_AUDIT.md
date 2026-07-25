# Codex — auditoría de frontera ts_recv/ts_event, ronda 009

## Hecho observado

La descarga autorizada se detuvo:

- 2/98 archivos descargados, validados y conservados;
- la tercera petición fue entregada pero el archivo temporal se descartó porque
  contenía un `ts_event` anterior a `start`;
- no se produjeron etiquetas.

La documentación oficial de `Historical.timeseries.get_range` aclara que
`start/end` filtran por **ts_recv** cuando el schema contiene ese campo. MBO
contiene `ts_recv`. Por definición, `ts_event` precede a `ts_recv`, por lo que
un registro con `ts_recv>=start` y `ts_event<start` es válido y esperado.

El validador confundió frontera de transporte con frontera causal.

## Riesgo simétrico al final

La etiqueta usa exchange-time:

```text
[t_decision, t_decision+5s)
```

Pedir hasta `t_decision+5s` por ts_recv puede truncar un Match Event cuyo
`ts_event` sea anterior al cutoff pero cuyo F_LAST se reciba milisegundos
después. Conservar un archivo así violaría V4; descartarlo después de pagarlo
repetiría el problema.

## Corrección propuesta

Separar solicitud y análisis:

```text
request por ts_recv:
  start = t_decision-100ms
  end   = t_decision+5s+100ms

label por ts_event:
  p0: último T-event ts_event<t_decision, lag<=100ms
  W:  t_decision<=ts_event<t_decision+5s
```

- Registros con `ts_event<request_start` son contexto de transporte válido.
- Registros con `ts_event>=label_end` se excluyen de la etiqueta.
- Todo T-event usado en p0 o W debe cerrar con F_LAST.
- El padding de 100 ms nunca entra en la etiqueta ni en predictores.
- Archivos que fallen se ponen en cuarentena; no se borran.

## Costo

El tercer request ya pudo generar cargo y se perdió localmente por el bug.
Costo cotizado:

```text
USD 0.055297400057
```

Proyección mínima si se repitiera sin padding:

```text
USD 5.810737153888
```

ya superior al tope USD 5.76. Primero debe convergerse la corrección, cotizar
las 96 ventanas pendientes con padding y pedir autorización nueva por el total
proyectado exacto.
