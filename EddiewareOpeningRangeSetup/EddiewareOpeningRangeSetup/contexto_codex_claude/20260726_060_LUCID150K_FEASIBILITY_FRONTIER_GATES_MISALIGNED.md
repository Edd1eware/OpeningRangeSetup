# 060 — Frontera de factibilidad Lucid 150K: los gates de V1–V14 están desalineados con el objetivo

Fecha: 2026-07-26
Autor: Claude
Estado: **hallazgo estructural. Detiene la ejecución de V14 tal como está preregistrada.**

## 1. Qué se hizo y por qué

El handoff `plan_edge_codex.md` ordena correr V14 y, si falla, seguir con V15/V16/V17.
Antes de gastar sesiones en la hipótesis 14, se hizo la pregunta que las trece
anteriores nunca hicieron: **¿qué forma tiene que tener un edge para pasar una
LucidPro 150K en 63 sesiones?**

Se construyó un mapa de factibilidad por Monte Carlo con las reglas reales de la
cuenta, no con métricas genéricas de backtest.

Scripts (nuevos, deterministas, `seed=20260726`):

```text
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\lucid150k_feasibility\feasibility_map.py
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\lucid150k_feasibility\feasibility_map_rr.py
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\lucid150k_feasibility\v14_gate_sufficiency.py
```

Modelo de cuenta: target `+$9,000` sobre balance EOD, floor
`min(peak_EOD - 4500, +100)`, DLL blando `$2,700` con corte operativo en
`$2,200`, máximo 10 minis, 63 sesiones, NQ mini `$5.00`/tick, coste total
`4 ticks` por round turn (estándar heredado de Codex). Bracket fijo, sin
trailing, `5,000` caminos por celda (`20,000` en el test de suficiencia).

Umbrales de aceptación congelados **antes** de simular:
`P(pass) >= 0.70` y `P(breach) <= 0.10`.

R:R `1:1` se respeta como **mínimo**, por regla del usuario. El barrido explora
`1:1` y hacia arriba (`1.5`, `2.0`, `2.5`, `3.0`). Nunca por debajo.

## 2. Resultado 1 — a 1:1 puro con baja frecuencia no existe configuración viable

`1,440` celdas simuladas a bracket `1:1`, `36` viables. Ninguna con win rate
por debajo de `0.65`.

| R:R | trades/día | WR mínimo | stop | contratos | PF req | EV neta | P(pass) | P(breach) | días medianos |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1:1 | 0.5 | ninguna | — | — | — | — | — | — | — |
| 1:1 | 1.0 | 0.68 | 60t | 3 | 1.86 | +17.6t | 0.863 | 0.090 | 29 |
| 1:1 | 2.0 | 0.64 | 60t | 2 | 1.56 | +12.8t | 0.844 | 0.098 | 30 |
| 1:1 | 3.0 | 0.64 | 60t | 2 | 1.56 | +12.8t | 0.903 | 0.091 | 21 |
| 1.5:1 | 2.0 | 0.54 | 40t | 2 | 1.49 | +10.0t | 0.785 | 0.072 | 37 |
| 2:1 | 1.0 | 0.52 | 60t | 2 | 1.96 | +29.6t | 0.897 | 0.069 | 27 |
| 2:1 | 2.0 | 0.46 | 60t | 1 | 1.54 | +18.8t | 0.762 | 0.035 | 39 |
| 2.5:1 | 2.0 | 0.40 | 60t | 1 | 1.52 | +20.0t | 0.780 | 0.067 | 36 |
| 3:1 | 2.0 | 0.36 | 60t | 1 | 1.55 | +22.4t | 0.798 | 0.090 | 33 |

Lecturas:

1. A media entrada por sesión, `1:1` es infactible a cualquier win rate del
   barrido y a cualquier tamaño legal.
2. Subir el R:R por encima del mínimo exigido baja el win rate requerido de
   `0.64` a `0.36`. Es la palanca más barata y V1–V13 nunca la movieron; todas
   diagnosticaron a `1:1` fijo.
3. El stop ganador siempre es el grande (`60t`). Con coste de `4 ticks`, los
   stops chicos pagan proporcionalmente más fricción.

## 3. Resultado 2 — el gate de V14 es insuficiente por construcción

V14 exige `frecuencia >= 2.0 trades/mes`, `EV > +0.12R`, `PF > 1.35`, target
`2R`, stop `40t`. Se simuló una estrategia que pasa esos gates **exactamente en
el umbral** (`PF 1.35` a `2R` implica `WR = 0.403`, `EV = 0.209R`).

Trades esperados en 63 sesiones: `6.0`. R neta acumulada esperada: `1.25R`.

| contratos | riesgo $/trade | P(pass) | P(breach) | mediana $ |
|---:|---:|---:|---:|---:|
| 1 | 220 | 0.0000 | 0.0000 | 100 |
| 2 | 440 | 0.0000 | 0.0003 | 200 |
| 3 | 660 | 0.0004 | 0.0184 | 300 |
| 5 | 1,100 | 0.0214 | 0.1263 | 500 |
| 7 | 1,540 | 0.0919 | 0.3878 | −420 |
| 10 | 2,200 | 0.2009 | 0.4202 | −600 |

**V14 puede pasar como ciencia y seguir siendo inútil para el objetivo.** Con
sizing prudente la probabilidad de pasar la cuenta es cero; la única forma de
subirla es apostar 7–10 minis, y ahí la probabilidad de quemar (`39–42%`)
supera cuatro veces el gate de breach.

Esto no es un defecto de la hipótesis overnight. Es aritmética de la cuenta: con
`2 trades/mes` no hay PF que alcance.

## 4. La métrica correcta: throughput, no PF

R necesaria para llegar a `+$9,000`, según riesgo por trade:

| contratos (stop 40t) | riesgo $/trade | R neta necesaria |
|---:|---:|---:|
| 1 | 220 | 40.9R |
| 2 | 440 | 20.5R |
| 3 | 660 | 13.6R |
| 5 | 1,100 | 8.2R |
| 10 | 2,200 | 4.1R |

El MLL de `$4,500` acota el riesgo prudente a unos `$600` por trade (7–8
pérdidas seguidas antes de quemar). Eso fija el requisito real:

```text
EV_en_R  x  N_trades  >=  ~15R  en 63 sesiones
```

Expresado como caudal, que es como debe medirse de ahora en adelante:

```text
$9,000 / 63 sesiones = $143/sesión = 28.6 ticks/sesión con 1 mini
                                   = 14.3 ticks/sesión con 2 minis
                                   =  9.5 ticks/sesión con 3 minis
```

Contraste con el mejor edge medido en todo el proyecto —primer breakout UP,
`+3.17t` a `8.4 trades/mes` (`0.4/día`)— que produce `1.27 ticks/sesión`.

**La brecha es de 7.5x, y es de caudal, no de calidad.** Trece hipótesis
optimizaron EV por trade y PF mientras la cuenta exige ticks por sesión.

## 5. Consecuencias para el plan de Codex

| Paso del plan | Veredicto | Motivo |
|---|---|---|
| Paso A: correr V14 tal cual | **Suspendido** | Aunque pase, `P(pass cuenta) = 0.00` con sizing prudente |
| Paso B: gates V14 | **Reemplazar** | Miden calidad, no caudal; `>=2 trades/mes` es 20x insuficiente |
| Paso C: V15 walk-forward | Útil sólo si el candidato genera `>=1 trade/día` | Mismo problema de frecuencia si no |
| Paso C: V16 MBO causal | Bajo | 4 representaciones ya fallaron; bloque 2024 sellado |
| Paso C: V17 régimen multiinstrumento | **Sube a prioridad 1** | Es el único mecanismo que multiplica caudal |
| Paso E: simulación Lucid al final | **Mover al principio** | Ya se hizo aquí; es un filtro de diseño, no un informe final |

El bug de separación DEV/pseudo que Codex señala en `run_v14.py` es real y sigue
siendo válido, pero es secundario: no vale la pena arreglar el script de una
hipótesis que no puede alcanzar el objetivo aunque acierte.

La data overnight de V14 ya está pagada (`~US$10.84`) y no se desperdicia: sirve
como feature de régimen para la vía de caudal, no como disparador único diario.

## 6. Gates nuevos propuestos, congelados antes de mirar cualquier outcome

Toda hipótesis a partir de aquí debe cumplir, en validación temporal:

- Caudal: `>= 1.0 trade/día` de media, equivalente a `>= 21 trades/mes`.
- EV neta: `>= +8 ticks/trade` después de `4 ticks` de coste.
- Producto: `>= 9.5 ticks/sesión` con `3 minis` o mejor combinación equivalente.
- R:R `>= 1:1` estricto, con preferencia explícita por `2:1` porque baja el win
  rate requerido de `0.64` a `0.46`.
- Estabilidad: todos los años del periodo de desarrollo positivos.
- Simulación Lucid con estos scripts antes de declarar candidato: `P(pass) >= 0.70`,
  `P(breach) <= 0.10`.

## 7. Siguiente acción

Reorientar la búsqueda de "encontrar un setup con PF alto" a "encontrar una
cartera con caudal suficiente". Prioridad: agregación multiinstrumento y
multiventana con el mismo mecanismo, midiendo ticks por sesión.

No se abrió el pseudo 2024. No se abrió el holdout `2020-01-01..2022-04-22`.
No se optimizó ningún umbral de V14.

`INFORMATION_STATUS=LUCID150K_FEASIBILITY_FRONTIER_GATES_MISALIGNED`
