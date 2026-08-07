# Consenso Claude + Codex: integridad del target post-LB

Fecha: 2026-07-27

Estado: `CONSENSUS_FINAL_NO_RESIDUAL_DISAGREEMENT`

Este documento registra el acuerdo alcanzado después de tres rondas de
auditoría independiente y conciliación. No abre features, modelos, validation
ni holdout.

## Veredicto del 0/60

```text
MUNDO_A_DATA_INCOMPLETE
```

Las primeras 60 fechas son 2022-04-04 a 2022-06-24. Su cobertura:

- 58 `marketdepth.dat` contienen sólo un header de 33 bytes, template 93,
  `tick_size=0` y `lot_size=0`;
- dos no tienen archivo depth;
- ninguna tiene depth/MID utilizable.

El detector trade-only congelado sí es alcanzable en ese mismo intervalo:

- 57/60 fechas tienen trades utilizables;
- las 57/57 contienen al menos un LB;
- 1,868 LB en total;
- mínimo 7 y máximo 85 LB por sesión legible;
- las tres exclusiones trade son Viernes Santo, Memorial Day y Juneteenth.

La corrida es una auditoría mecánica descriptiva. No tuvo hipótesis estadística
prerregistrada, no prueba estacionariedad del régimen y no puede cambiar ningún
umbral.

El antecedente `n=111` significaba 111 eventos LB sobre cinco sesiones smoke,
no 111 sesiones sobre 195. Existe además otro 111 no relacionado: 111 fechas
weekday con depth presente en el barrido outcome-blind de 2022.

## Regresión V1 frente a V2

En el solapamiento 2022-08-01 a 2022-08-05:

- V1 MID/8t/5s/250ms: 111 filas;
- caché V2: 111 filas;
- diferencia simétrica de `LB_ID`: 0;
- igualdad exacta de régimen y métricas de trayectoria: PASS;
- distribución idéntica: 47 continuación, 40 reversión, 23 no expansión y
  una ambigua.

No hay evidencia de regresión V1 a V2 en el solapamiento comprobable.

## Decisiones conjuntas

1. Se conservan sin cambios 8 ticks, 5 segundos, MID, ambigüedad 250 ms,
   spread 1–4 ticks y `AMBIGUOUS` como abstención no fusionada.
2. No se baja ni modifica ningún gate científico.
3. `splits.discovery` no se recorta. La cobertura real se documenta mediante
   `depth_coverage_manifest.csv`.
4. Las cinco sesiones smoke permanecen en el discovery primario porque así
   estaba congelado. El reporte con/sin ellas será sólo sensibilidad
   diagnóstica, nunca selección ni rescate.
5. La cobertura `depth_present / weekdays` se reporta y no se gatea.
6. El gate mecánico será
   `evaluated / eligible_after_frozen_QC = 1.00`; las exclusiones QC congeladas
   se reportan aparte.
7. La caché parcial no se agrega, no se reanuda y no se borra. Se mueve de
   forma reversible a cuarentena sin leer las etiquetas no-smoke.
8. No se abre ninguna feature, modelo, validation 2023, holdout 2024 ni
   2025–2026 antes de cerrar la puerta target-only.
9. No se ejecuta `git add` ni `git commit` sin autorización explícita del
   usuario. Se registra que `volatility_trigger/` está sin seguimiento Git.

## Defecto de estado vigente de quote

El prerregistro exige que la referencia a `tLB` sea vigente, tenga edad máxima
de 250 ms y spread entre 1 y 4 ticks.

La implementación anterior podía devolver la última quote válida aunque el
estado vigente del libro ya fuera inválido, porque seleccionaba el precio desde
`quotes.ticks` pero medía frescura contra cualquier `depth_ticks`. Una prueba
sintética reprodujo un libro sin ask que aun devolvía MID y edad 0 ms.

Tratamiento acordado:

1. crear un test rojo no marcado `xfail`;
2. medir impacto sólo en las cinco sesiones smoke;
3. corregir la implementación como defecto de proceso, sin tocar 250 ms ni
   spread 1–4;
4. emitir enmienda y hash nuevos antes de regenerar discovery;
5. volver a ejecutar la auditoría V1 completa sobre las cinco sesiones smoke;
6. aplicar mecánicamente la jerarquía congelada `8→12→4→16`.

Si el primer threshold que pasa deja de ser 8, se acata. Está prohibido
conservar 8 por inercia o elegir por conveniencia.

## Bloqueos

Target-only no puede reanudarse hasta que:

- el test de estado inválido pase en verde;
- se emita la enmienda de integridad;
- se repita la auditoría V1 y se aplique la jerarquía congelada;
- el freeze V3 incluya todas las dependencias load-bearing y sus hashes;
- la caché parcial esté en cuarentena.

`INFORMATION_STATUS=CLAUDE_CODEX_DATA_INTEGRITY_CONSENSUS_FINAL`
