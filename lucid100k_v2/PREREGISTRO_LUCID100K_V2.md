# Preregistro LUCID100K-V2 — familia RR 1:1 con selección era-blind

Fecha: 2026-07-25
Autor: Claude Fable
Estado: **CONGELADO ANTES DE GENERAR NADA**

## 0. Qué falló en V1 y por qué esto no es minar

V1 (`fixed 60/60`, UP-only, 2 contratos) dio **P(pass) = 29.04%** contra un gate
de 30%. Diagnóstico: con 2 contratos, el SL de 60 ticks son $600 y el MLL de
$3,000 absorbe **solo 5 pérdidas seguidas**.

El cuello de botella **no es la señal** — es la **geometría del bracket y el
tamaño** frente al límite de la cuenta. La señal (primer breakout UP) queda
intacta y congelada.

El goal fija `RR ≥ 1:1` pero **no fija la magnitud** del bracket. Elegir magnitud
y tamaño es diseño de riesgo, no búsqueda de señal. Para que no sea minado:

> **Toda la selección se hace sobre DEV 2022-2023 y se aplica congelada a
> FRESH 2024-2026, que decide una sola vez.**

## 1. Señal congelada (idéntica a V1, no se toca)

```text
entrada = primer breakout del OR 09:30-09:31, SOLO direccion UP,
          al nivel del OR, desde 13:31:00 UTC
comision = 2.0 ticks | NQ $5/tick
```

## 2. Espacio de diseño (se recorre SOLO en DEV)

```text
bracket RR 1:1  ->  TP = SL ∈ {40, 60, 80, 100} ticks
tamano          ->  {1, 2, 3} contratos
```

12 combinaciones. Todas cumplen RR exactamente 1:1 por construcción.

Etiquetas a generar desde barras 1s con la **regla pesimista** ya usada: si en la
misma barra se tocan TP y SL, gana el SL.

## 3. Regla de selección — declarada ahora

```text
Para cada una de las 12 combinaciones se corre el MC de evaluacion SOLO sobre
DEV 2022-2023. Se elige la que maximiza P(pass)_DEV.
Desempate 1: menor tamano (menos capital en riesgo)
Desempate 2: menor TP (antes al objetivo)
La combinacion ganadora se CONGELA y se aplica sin cambios a FRESH.
```

**FRESH no participa en la selección.** Se abre una sola vez, ya elegida la
combinación.

## 4. Simulación de la evaluación (Lucid 100k)

```text
target = +$6,000  |  MLL trailing = $3,000 desde el pico  |  NQ $5/tick
1 trade por dia habil, maximo 120 dias por intento
10,000 intentos, seed 0x22f9cadf098b1625
```

## 5. Gate (los cuatro, sobre FRESH, con la combinación congelada)

| # | Criterio | Umbral |
|---|---|---|
| G1 | **P(pasar) por intento** | **≥ 30%** |
| G2 | EV neto por trade | > 0 |
| G3 | WR | > breakeven del bracket elegido |
| G4 | Años con EV neto > 0 | ≥ 2 de 3 |

`breakeven WR = (TP + 2) / (2·TP)` por la comisión de 2 ticks.

PASS en los cuatro → **edge encontrado** para el goal, se documenta y se propone
forward. Un fallo = rechazada; no se prueba una 13ª combinación ni se relaja el
umbral.

## 6. Prohibiciones

No se añaden brackets fuera de {40,60,80,100} ni tamaños fuera de {1,2,3}. No se
cambia la señal (siempre primer breakout UP). No se selecciona mirando FRESH. No
se excluye ningún año. No se repite el MC con otra semilla.

`INFORMATION_STATUS=LUCID100K_V2_PREREGISTERED_NO_RESULT`
