# H3 — Liquidity Burst como filtro de día: FAIL, relación INVERSA, y 82% lookahead

Fecha: 2026-07-25 · `PREREGISTRO_H1_H4.md` + `ADDENDUM_H3_001.md`
Universo: 240 sesiones, replay sistemático 2025-2026 (2022-24 excluido por sesgo)

## 1. Veredicto: FAIL (4 de 5 gates)

| Gate | Umbral | Obtenido | |
|---|---|---:|---|
| G1 EV neto > 0 | > 0 | **−4.477** | FAIL |
| G2 PF > 1.15 | > 1.15 | **0.790** | FAIL |
| G3 Años EV>0 (2 de 2) | 2 de 2 | **0 de 2** | FAIL |
| G4 Frecuencia ≥ 4/mes | ≥ 4 | 9.25 | PASS |
| G5 Supera sin filtro | > +3.358 | **−4.477** | FAIL |

## 2. La relación existe, pero es la INVERSA de la hipótesis

| Grupo | n | Trades/mes | WR % | PF | EV neto |
|---|---:|---:|---:|---:|---:|
| Sin filtro | 240 | 18.46 | 43.75 | 1.189 | +3.358 |
| **Días CON LB** | 111 | 9.25 | 36.94 | 0.790 | **−4.477** |
| **Días SIN LB** | 129 | 9.92 | 49.61 | 1.685 | **+10.101** |

Diferencia de **14.6 ticks netos**, consistente en ambos años:

| Year | Con LB | Sin LB |
|---|---:|---:|
| 2025 | −5.117 | +10.918 |
| 2026 | −3.029 | +8.523 |

La hipótesis decía "LB marca los días que vale la pena operar". El dato dice lo
contrario con fuerza: **los días con Liquidity Burst son los días en que el
breakout del OR falla.**

## 3. PERO: el 82% es lookahead — no es operable como filtro de entrada

Verificación de causalidad (obligatoria antes de celebrar nada):

```text
entrada del breakout : mediana 09:31:09   (p90 09:32:06)
primer LB del dia    : mediana 09:32:30   (p10 09:31:02, p90 09:37:53)

de 199 dias con ambos datos:
   LB antes o igual a la entrada (usable) :  35  (18%)
   LB despues de la entrada (LOOKAHEAD)   : 164  (82%)
mediana LB - entrada = +59 segundos
```

En el momento de entrar (09:31:09) **todavía no sabes si habrá un LB**. Filtrar
por "este día tiene LB" usa información del futuro en 82% de los casos.

El resultado de la sección 2, por espectacular que parezca, **no se puede operar
así**. Habría sido un falso descubrimiento clásico.

## 4. El reencuadre que SÍ es causal

El LB ocurre en mediana 59 segundos **después** de la entrada. Eso no sirve para
decidir si entrar, pero sí para decidir **si seguir dentro**:

> Si estás en un breakout del OR y aparece un Liquidity Burst en el minuto
> siguiente, ese es el aviso de que el breakout va a fallar.

Eso es plenamente causal: el evento ocurre, luego actúas. Y encaja con la lógica
de ATRAPADOS (fade tras breakout fallido) y con "el LB localiza volatilidad, no
dirección".

**No lo pruebo hoy.** Sería post hoc sobre el mismo dataset donde acabo de ver la
relación. Requiere su propio preregistro y, dado que la señal se descubrió aquí,
un holdout distinto o forward.

## 5. Lo que deja establecido

1. H3 tal como se preregistró: **rechazada**.
2. Existe una relación fuerte y estable LB ↔ fallo del breakout, en dirección
   contraria a la esperada.
3. Como **filtro de entrada es inutilizable** (82% lookahead).
4. Como **señal de salida/reversa es plausible y causal**, y es la hipótesis más
   concreta que deja el día.

`INFORMATION_STATUS=H3_REJECTED_INVERSE_RELATION_LOOKAHEAD_82PCT`
