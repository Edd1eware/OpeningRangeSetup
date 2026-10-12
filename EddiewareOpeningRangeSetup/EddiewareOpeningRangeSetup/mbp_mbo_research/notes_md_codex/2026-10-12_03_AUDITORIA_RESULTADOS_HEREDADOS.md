# Auditoría de resultados heredados

Fecha:2026-10-12. Estos son reportes previos, no la corrida corregida del setup confirmado hoy.

## Regla completa antigua

Fuente:`C:/Users/k_99_/Desktop/codding/MBP_MBO/reports/full_spec_far.csv`.

150sesiones entre9marzo y9octubre2026;26operaciones reales, cada una repetida para5RR. Contar130filas de trade como130observaciones independientes sería incorrecto.

Coste heredado supuesto:1.8ticks por operación.

| RR | Ganadores de26 | EV neto ticks/contrato | IC95% bootstrap descriptivo | EV neto R con riesgo fijo |
|---|---:|---:|---|---:|
|1:1|12|−3.262|[−36.723,+30.123]|−0.1034|
|1:1.5|11|+6.681|[−34.396,+48.700]|+0.0312|
|1:2|9|+10.969|[−36.492,+62.123]|+0.0120|
|1:2.5|7|+12.700|[−41.954,+72.816]|−0.0842|
|1:3|6|−1.877|[−55.916,+60.392]|−0.2124|

Los intervalos remuestrean operaciones con100,000réplicas; todas las filas tienen26observaciones, y todos los intervalos incluyen0 incluso antes de ajustar por probar5RR. No certifican OOS.

RR1:1:WR46.15%,ICexactobinomial95%[26.59%,66.63%],suma−84.8ticks netos,PFneto0.9233. Bloques de5sesiones calendario incluyendo días sin trade danIC95%deEV[−34.200,+29.937]ticks.

Con SL variable, EV en ticks por contrato y EV enR para riesgo fijo son cosas distintas. RR1:2.5 es positivo en ticks y negativo enR; elegirlo por la mayor media en ticks no demuestra que mejore una cuenta con riesgo monetario fijo.

En RR1:1.5 y1:2.5,14de26TP se expresan en medios ticks. Debe imponerse una política de redondeo ejecutable antes de tratar esas alternativas como negociables.

## Alcance y motivos para recalcular

- Detector Python con guardas de extremos diagonales invertidas.
- VWAP antigua calculada con cierres de1s, distinta de la fuenteClose deM1 de ATAS.
- Filtros adicionales antiguos:30–120ticks, pool de imbalances previos, revisitas y ausencia de cambios de color. No corresponden automáticamente a las reglas confirmadas ahora.
- Toda la temporada2026 ya fue inspeccionada y motivó candidatos. No recuperar independencia llamandoOOS a un corte nuevo.

El corte exploratorio primeras100sesiones calendario da20trades,+7.15ticks netos/trade pero−0.0293R;últimas50da6trades,−37.967ticks y−0.3502R. No confundirlo con un corte por primeras100señales.

## Control previo del footprint

`reports/footprint_incremental.csv`:145primeras rupturas,26pasan y119fallan. Bracketdiagnóstico60/60ticks y30minutos.

- Ventaja direccionalDmedia:pasan−13.846ticks;fallan+1.517ticks.
- Diferencia−15.363ticks;IC95%descriptivo[−39.457,+9.735].
- No demuestra aporte favorable del filtro; tampoco prueba ausencia universal de edge ni sustituye a la política de esperar velas posteriores.
- Hay un nuevo control independiente con bordes correctos y verificación del ejemplo de imagen.

## Otros reportes

`entry_mode_comparison.csv` contiene49celdas;su p mínimo reportado contra breakeven neto es0.1329. Ninguna alcanza0.05sin ajuste.

`barrier_engine.csv` contiene18políticas de otras familias;todas sus mediasOOS son negativas con coste1.8ticks. Este alcance no refuta todo el order flow ni el setup actualizado.

Las notas previas `CODEX_RONDA2.md` documentan candidatos derivados de145eventos completos antes del split, medianaSLcalculada conIS+OOS y placebo degenerado. La nota `2026-10-12_RESULTADO_TAPE.md` simula LucidFlex, mientras la captura actual corresponde a LucidPro. No trasladar sus probabilidades ni el umbral de+2.5ticks requerido a otra política sin reconstruir sus supuestos.

## Conclusión limitada

No hay edge demostrado en estos reportes heredados. Esto no prueba que sea imposible encontrarlo. Antes de mejorarRR,filtros o sizing, hace falta reproducir correctamente la señal y la ejecución; después separar búsqueda exploratoria de validación independiente.
