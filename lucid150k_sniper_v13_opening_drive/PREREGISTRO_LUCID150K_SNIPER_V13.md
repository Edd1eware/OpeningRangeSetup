# Prerregistro — LUCID150K-SNIPER-V13 Opening Drive Pullback

Fecha de congelación: 2026-07-26

## Objetivo

Probar una familia independiente de los OR/IB breakouts V1–V12: un impulso de
apertura direccional y eficiente que retrocede de forma controlada y después
reanuda. Una operación máxima por sesión NQ.

## Datos y particiones

- OHLCV-1s NQ, horario interpretado con `America/New_York`.
- DEV: 2022-04-25 a 2023-12-31.
- Pseudo-validación: 2024, sólo si pasa todos los gates DEV.
- Stress descriptivo ya visto: 2025-01-01 a 2026-06-30.
- Holdout 2020-01-01 a 2022-04-22 permanece sin descargar.

## Regla exacta

1. Impulso: 09:30:00–09:44:59 NY.
2. `body = close_0945 - open_0930`; `range = high15 - low15`.
3. Elegible si `abs(body)/range >= 0.70` y el cierre queda en el 20% exterior
   del rango en la dirección del body.
4. Desde 09:45 hasta 10:45, exigir retroceso hasta el 50% del body.
5. Se invalida si antes de la entrada el precio toca o cruza el open 09:30.
6. Tras el retroceso, exigir un cierre de 1 s que recupere el nivel 75% del body.
   Entrada en el open de la siguiente barra, más un tick adverso de slippage.
7. Stop fijo 40 ticks; target bruto 80 ticks (2R). Coste total 4 ticks.
8. Gestión principal: al alcanzar +1R, break-even neto de costes y trailing de
   1R; salida máxima 15:55 NY. Diagnóstico separado: target/stop fijo 1:1.

## Gates DEV congelados

- `n >= 50`.
- Frecuencia `>= 2.0` operaciones/mes.
- EV neta `> +0.12R`.
- PF `> 1.35`.
- Ambos años positivos.
- `>=75%` de las cuatro mitades positivas.
- EV trailing menos EV fija 1:1 `>= -0.05R`.

## Gates pseudo-validación 2024

- `n >= 25`, EV `>0`, PF `>1.15`.
- Límite inferior del bootstrap 95% de EV `> -0.08R`.

Sólo el cumplimiento íntegro autoriza cotizar/descargar el holdout.
