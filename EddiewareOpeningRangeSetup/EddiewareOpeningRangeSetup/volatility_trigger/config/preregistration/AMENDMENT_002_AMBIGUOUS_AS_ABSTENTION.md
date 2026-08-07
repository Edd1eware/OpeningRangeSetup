# Enmienda 002: AMBIGUOUS como abstención

Fecha: 2026-07-27

Estado: `POST_SMOKE_BEFORE_DISCOVERY_MODELS`

Esta enmienda aclara el estatus epistemológico de
`POST_LB_REGIME_V2_RESOLVED_WITH_ABSTENTION`.

La definición V2 se formuló después de observar la auditoría de etiquetas del
set técnico de cinco sesiones:

```text
CONTINUATION 47
REVERSAL     40
NO_EXPANSION 23
AMBIGUOUS     1
```

Por tanto, V2 no se presenta como un prerregistro virgen. Es una enmienda
post-smoke y anterior a discovery/modelos.

La acción estaba autorizada por el documento rector:

- su sección de smoke permite auditoría de etiquetas;
- su sección de abstención permite no forzar continuación o reversión cuando
  el régimen es ambiguo.

La enmienda no fusiona ni reetiqueta trayectorias:

- clases resueltas: continuación, reversión y no expansión;
- `AMBIGUOUS` se conserva como outcome separado;
- `AMBIGUOUS` se excluye de la pérdida del clasificador resuelto y se reporta
  como abstención/calidad de resolución.

El prerregistro V2 existente conserva SHA-256:

```text
DF0DB190272272CDA437C84D1F0C7AA0A07F6649F1496D5D57D79CC4434D7A02
```

Ninguna feature, modelo, validation ni holdout se abrió para tomar esta
decisión.

`INFORMATION_STATUS=AMENDMENT_002_POST_SMOKE_PRE_DISCOVERY_RECORDED`
