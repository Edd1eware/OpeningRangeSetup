# Consenso final Claude–Codex: target post-LB V3

Fecha: 2026-07-27  
Claude session: `f55f1e23-3599-4033-b7a3-9b113bccc3c8`  
Alcance: auditoría post-run, estrictamente de solo lectura  
Target: `POST_LB_REGIME_V3_CURRENT_QUOTE_RESOLVED_WITH_ABSTENTION`

## Alcance del consenso

Este documento acepta el veredicto de la corrida V3. No modifica el
prerregistro, no rescata el target, no autoriza una V4 y no abre features,
modelos, validation ni holdout.

Claude recalculó independientemente los gates, la consistencia interna y la
causalidad. Codex recomputó además los 54 hashes de los tres freezes y los
cuatro hashes del manifiesto final. Coinciden en el veredicto, los gates y las
prohibiciones; queda registrada una reserva conjunta sobre la continuidad
gate–regla.

## Veredicto conjunto

```text
REGIME_V3_TARGET_DISCOVERY_FAIL
DATA_QUALITY_FAIL
CONSENSO: SI
```

La cobertura de referencia preregistrada era una condición necesaria:

```text
observado = 2560 / 2727 = 0.9387605427209388
gate      = 0.95
resultado = FAIL
```

El gate se evalúa por conjunción. Que los demás gates pasen no compensa este
incumplimiento.

## Reserva de continuidad gate–regla

Esta reserva queda registrada, pero no es accionable dentro de V3.

El gate de cobertura `>=0.95` preexistía a `AMENDMENT_003`: figura en el
prerregistro V1 y en `post_lb_regime_v2_config.json`, ambos congelados antes de
la corrección. No consta en el expediente ninguna derivación numérica de ese
valor; sólo su preexistencia y su retención.

Bajo la implementación laxa, la cobertura de referencia en el set técnico de
5 sesiones era 111/111 = 1.000000, por lo que el listón nunca estuvo sometido a
tensión. Al corregir la validez exigiendo estado vigente del libro, la
cobertura pasó a 106/111 = 0.954955 en ese mismo set técnico y a 2560/2727 =
0.938761 en discovery.

El gate se retuvo sin volver a examinarse bajo la regla endurecida. Queda
registrado que el listón nunca fue evaluado frente a la regla estricta antes
de abrir discovery.

Esta reserva **no autoriza modificar el gate post-hoc, no rescata el target y
no altera el veredicto `REGIME_V3_TARGET_DISCOVERY_FAIL`**. Su única función es
que cualquier consideración futura de la Opción 2 distinga la parte del
déficit atribuible a calidad de dato de la atribuible a continuidad de
proceso.

## Gates recalculados

| Gate | Umbral | Observado | Estado |
|---|---:|---:|---|
| LB válidos | >=500 | 2560 | PASS |
| mínimo por clase resuelta | >=100 | 525 | PASS |
| meses por clase resuelta | >=6 | 6 | PASS |
| máximo share de una clase resuelta | <=0.70 | 0.5654552559593591 | PASS |
| TVD BUY/SELL resuelta | <=0.15 | 0.02574124977093642 | PASS |
| máxima concentración mensual | <=0.35 | 0.29523809523809524 | PASS |
| share `AMBIGUOUS` | <=0.10 | 0.000390625 | PASS |
| cobertura de referencia | >=0.95 | 0.9387605427209388 | **FAIL** |
| proceso evaluado/elegible | =1.00 | 104/104 = 1.00 | PASS |

Distribución exacta: 587 `CONTINUATION`, 525 `REVERSAL`, 1447
`NO_EXPANSION` y 1 `AMBIGUOUS`.

## Integridad y causalidad

- Los freezes de auditoría técnica, target V3 y runner preceden a la apertura
  de las etiquetas correspondientes.
- Se verificaron todos los hashes de 13, 18 y 23 archivos de los tres
  manifiestos; cero faltantes y cero discrepancias.
- Los cuatro hashes del manifiesto final coinciden.
- `data_audit.csv` contiene 195 sesiones: 104 `PASS`, 80 depth
  header-only/zero-scale, 7 exclusiones por QC temporal congelado, 4 depth
  missing y 0 `PROCESS_ERROR`.
- Las 2560 etiquetas tienen `lb_quote_ticks <= publish_ticks`.
- El outcome empieza estrictamente después de `publish_ticks`
  (`searchsorted(..., side="right")`).
- No hay `lb_id` duplicados.
- No hay cotizaciones cruzadas/bloqueadas ni inconsistencias del MID.
- El spread observado está entre 1 y 4 ticks; edad depth máxima 95 ms y lag
  máximo de quote-group 188 ms.
- La sensibilidad sin las cinco fechas técnicas también falla por cobertura
  (`0.9380733944954128`) y no participa en `primary_pass`.
- No se detectó lookahead, selección post-hoc ni overfit. No se ejecutaron
  features ni modelos.

## Jerarquía consumida

La jerarquía `8 -> 12 -> 4 -> 16` fue consumida una sola vez. Queda prohibido:

- volver a 8, 12 o 4 ticks;
- recalcular esos thresholds sobre discovery;
- cambiar threshold u horizonte usando el resultado;
- fusionar `AMBIGUOUS`;
- usar la sensibilidad como selección o rescate.

La prohibición seguirá siendo relevante porque 8 y 12 ticks fallaron TVD en el
set técnico con 0.1677 y 0.1875 sobre sólo 106 observaciones de cinco sesiones,
mientras que el TVD de la definición congelada a escala discovery fue 0.0257
con 2559 observaciones resueltas. Esa diferencia no autoriza recalcular 8 o 12
ticks con las etiquetas de discovery ya abiertas.

## Riesgo post-hoc nuevo y prohibición explícita

La auditoría encontró que excluir sólo las dos peores sesiones por cobertura
de LB cambiaría artificialmente el resultado:

| Exclusión | Cobertura resultante |
|---|---:|
| ninguna | 0.9387605427209388 |
| excluir 2022-10-14 | 0.9474463360473723 |
| excluir 2022-10-14 y 2022-10-21 | 0.953880764904387 |

Por tanto, queda prohibido construir una regla de calidad de sesión a partir
de `reference_coverage`, `valid_reference_bursts`, outcomes o cualquier
estadístico condicionado a los LB ya observados. Excluir esas sesiones ahora
sería selección post-hoc.

## Hecho

- Diagnóstico 0/60 corregido: depth incompleto, no regresión del detector.
- Cobertura outcome-blind 2022 congelada.
- Bug de estado vigente de quote reproducido, corregido y probado.
- Auditoría técnica corregida 106/111.
- Definición V3 de 16 ticks / 5 s / MID / 250 ms congelada.
- `AMBIGUOUS` preservado como abstención.
- Caché V2 parcial puesta en cuarentena sin borrar.
- Corrida V3 completa y reproducible.
- 26/26 tests en verde.
- Features, modelos, validation y holdout permanecen cerrados.

## Pendiente

- `session_quality.csv`, exigido por la FASE 0 del documento rector.
- Reconciliar la calidad mecánica del libro con el gate de cobertura sin usar
  el resultado V3 para calibrar una exclusión.
- Equivalencia real C#–Python del detector LB v7 antes de desplegar en ATAS.
- Artefacto histórico ausente documentado en `ERRATA_001`.
- Sólo hay seis meses con depth utilizable en 2022 y julio es parcial; es un
  techo estructural que ningún gate corrige.
- Git permanece sin stage/commit y requiere autorización del usuario.

## Únicas continuaciones científicamente válidas

1. Aceptar este FAIL como terminal para el target 2022.
2. Sólo mediante un acuerdo Claude–Codex nuevo y autorización del usuario,
   preregistrar y hashear antes de cualquier recálculo una auditoría V4 de
   calidad de sesión outcome-blind. Sus criterios sólo podrían usar mecánica
   independiente del libro —por ejemplo bilateralidad válida, tasa de
   actualización y duración de gaps—, nunca cobertura alrededor de LB.

Si se considera la opción 2:

- se mantienen 16 ticks, 5 s, MID, 250 ms, spread 1–4 y el gate 0.95;
- se fija una sola regla antes de recalcular y queda prohibido iterarla;
- se reportan todas las sesiones excluidas;
- si excluye precisamente las dos sesiones que voltean el resultado, se
  escala al usuario por riesgo máximo de circularidad;
- si vuelve a fallar, el FAIL es definitivo;
- features, modelos, validation y holdout siguen cerrados.

No se eligió ni ejecutó ninguna de estas continuaciones en esta auditoría.
