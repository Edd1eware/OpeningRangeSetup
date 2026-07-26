# Prerregistro — LUCID150K-SNIPER-V14 Overnight Inventory Correction

Fecha de congelación: 2026-07-26

## Tesis

Una apertura RTH no debe evaluarse sólo por sus niveles. Si la mayor parte de
la sesión Globex NQ y ES permanece a un lado del cierre RTH anterior, existe
inventario overnight concentrado. Una vela inicial de cash que se mueve de
regreso al cierre anterior es evidencia observable de corrección.

## Datos y particiones

- NQ y ES continuos `ohlcv-1m`, desde 18:00 NY del día calendario anterior
  hasta 09:29 NY; coste cotizado medio `US$6.9769`, con margen 25%
  `US$8.7211`.
- NQ `ohlcv-1s` RTH para señal y ejecución.
- DEV: 2022-04-25 a 2023-12-31.
- Pseudo-validación 2024 sólo si pasa DEV.
- Stress descriptivo ya visto: 2025-01-01 a 2026-06-30.
- Holdout 2020-01-01 a 2022-04-22 permanece sin descargar.

## Regla exacta

1. El ancla de cada instrumento es el último close RTH disponible de la sesión
   anterior.
2. `inventory_fraction` es la fracción de cierres de 1 minuto Globex por encima
   de su ancla.
3. Inventario long si NQ `>=0.75`, ES `>=0.65` y ambos closes 09:29 están por
   encima del ancla. Inventario short si NQ `<=0.25`, ES `<=0.35` y ambos
   closes están debajo.
4. Confirmación de corrección: vela NQ 09:30:00–09:34:59 cierra contra el
   inventario y más cerca del ancla que su open.
5. Entrada contra inventario en el open de la primera barra de 1 s posterior a
   09:35, más un tick adverso.
6. Stop estructural cuatro ticks fuera del extremo de la vela cash de 5 minutos.
   Riesgo mínimo 20 ticks; si excede 80 ticks no hay trade.
7. Target bruto 2R; coste total 4 ticks. Al alcanzar +1R, break-even neto de
   costes y trailing 1R. Salida máxima 15:55 NY. Diagnóstico 1:1 fijo separado.
8. Máximo un trade por sesión.

## Gates DEV congelados

- `n >= 50`, frecuencia `>=2.0/mes`.
- EV neta `>+0.12R`, PF `>1.35`.
- Ambos años positivos y `>=75%` de mitades positivas.
- EV trailing menos EV fija 1:1 `>=-0.05R`.

## Gates pseudo-validación

- `n>=25`, EV `>0`, PF `>1.15`.
- Bootstrap 95% de EV con límite inferior `>-0.08R`.

Sólo el cumplimiento íntegro autoriza descargar el holdout.
