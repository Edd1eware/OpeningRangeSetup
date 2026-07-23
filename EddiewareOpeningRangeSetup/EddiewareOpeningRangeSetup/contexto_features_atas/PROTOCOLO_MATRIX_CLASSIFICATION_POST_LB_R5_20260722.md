# Protocolo congelado — MATRIX CLASSIFICATION TEST R5

## Pregunta primaria

¿La ruta causal DOM+tape que aparece **después** del Liquidity Burst y antes de `t_decision` permite separar:

- A: absorción limpia;
- B: breakout/continuación limpia?

C se conserva como trayectoria variable y posible abstención. No se usa para entrenar el clasificador binario.

## Alcance

- Historia X10 exclusivamente.
- DST 2025 y DST 2026: 256 sesiones, del 10/03/2025 al 17/07/2026.
- No se amplía a 2022–2024 si no aparece separación reproducible en este alcance.
- La lógica de entrada, TP, SL, RR y gestión no cambia.

## Ventana causal

La secuencia comienza en el propio Liquidity Burst:

```text
t_burst <= timestamp causal del evento <= t_decision
```

El contexto anterior al burst permanece disponible como snapshot de régimen, pero no se mezcla con la ruta post-LB.

El indicador v7 aplica el límite inferior al exportar. El análisis vuelve a aplicarlo como defensa independiente.

## Abstracción física

Las actualizaciones crudas se agrupan en bins causales de 100 ms. Cada bin se representa mediante una combinación reproducible de:

- `EFF`: agresión alineada con avance;
- `STALL`: agresión alineada sin avance proporcional;
- `CF`: contraflujo dominante;
- `WD`: reducción delante sin ejecución alineada simultánea observable;
- `CON`: reducción delante con ejecución alineada observable;
- `REF`: reposición delante;
- `REFP`: reposición repetida en el mismo nivel dentro de 500 ms;
- `BDP` / `BRF`: depleción o reposición detrás.

`CONT` y `REV` son outcomes, nunca predictores. `FAT`, `REC` y `ACC` se omiten del alfabeto primario porque MBP y una ventana cercana a un segundo no permiten identificarlos de manera inequívoca sin introducir reglas interpretativas.

## Objetos de investigación

Se generan:

- matrices de transición A, B y contraste A−B;
- tiempos, intensidad tape/DOM y persistencia;
- respuesta del precio a 100, 250 y 500 ms, sólo cuando sigue dentro de `t_decision`;
- bifurcaciones de historias de longitud 1 y 2;
- bigramas, trigramas y secuencias de longitud 4;
- estabilidad discovery/validation/holdout y BUY/SELL;
- ablation: snapshots, transiciones, secuencias y combinaciones;
- matrices de confusión, abstención, riesgo–cobertura y calibración;
- errores vinculados con el patrón causal dominante.

## Controles contra sobreajuste

- Las rutas candidatas para el modelo se seleccionan por soporte en discovery, sin usar la etiqueta A/B.
- Validation y holdout no seleccionan patrones ni features.
- Umbral binario congelado: 0.50.
- Umbral de abstención congelado: confianza 0.65.
- Se reportan bootstrap CI y permutation p-value.
- La clasificación por régimen se omite como rescate retrospectivo mientras haya sólo 31 casos A/B limpios.

## Criterio de capacidad

Para declarar separación se exige conjuntamente:

- al menos 20 A y 20 B en holdout;
- balanced accuracy ≥ 0.65;
- sensibilidad A y especificidad B ≥ 0.60;
- límite inferior del bootstrap CI de balanced accuracy > 0.50;
- permutation p-value ≤ 0.05;
- estabilidad BUY/SELL y cobertura explotable.

Un resultado prometedor que no cumpla todos los puntos no se presentará como capacidad operativa.

## Mensaje final de Telegram

La corrida terminará con exactamente una de estas conclusiones:

```text
YA SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO
```

o:

```text
NO SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO
me falta analizar: ...
```

Las variables faltantes se especificarán de acuerdo con el diagnóstico final.

## Puerta técnica

Antes de liberar las 256 sesiones se ejecutan cuatro fechas conocidas con bursts. Deben observarse:

- versión v7;
- DOM y tape;
- eventos exclusivamente post-LB;
- cero eventos posteriores a `t_decision`;
- reloj causal y orden de llegada monótonos;
- densidad suficiente de eventos por BurstId.

Si cualquier control obligatorio falla, la corrida larga se detiene.
