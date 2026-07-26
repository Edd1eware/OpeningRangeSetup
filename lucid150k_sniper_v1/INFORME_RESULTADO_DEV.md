# Resultado DEV — LUCID150K-SNIPER-V1

Fecha de ejecución: 2026-07-26  
Prerregistro SHA-256: `a173f38b9da683fcf170989c13e52d8e0d372fd08d368af018a5e5a17d8ea09a`  
Estado: **FAIL_NO_DOWNLOAD**

## Integridad

- 1,028 sesiones NQ/ES escaneadas con reloj `America/New_York`.
- 424 registros de operaciones entre todos los bloques observados.
- 0 errores de lectura o cálculo.
- No se abrió ni descargó el HOLDOUT 2020-01-01..2022-04-22.
- SHA-256 de `DEV_RESULT.json`:
  `0BF47D308A2E2FB5356DAC91737FB2F37ADF88779DA24D4AB6C45A74E05E40D8`.
- SHA-256 de `DEV_ALL_TRADES.csv`:
  `CF4AE8564A34873B9C82CF69F31AE68EFC6BCFE860A02CB057454A4267EC7196`.

## Resultado principal

| Familia | n DEV | EV neto | PF | EV 2022 | EV 2023 | Semestres positivos | PASS |
|---|---:|---:|---:|---:|---:|---:|---|
| ES lidera breakout NQ | 73 | -0.00374R | 0.9930 | +0.10985R | -0.11425R | 75% | No |
| Divergencia + reclaim NQ | 86 | -0.08614R | 0.8528 | -0.13815R | -0.04092R | 0% | No |

Las dos familias incumplieron EV > +0.05R, PF > 1.20 y dos años
positivos. Por eso no se seleccionó familia, no se consultó PSEUDO_VAL como
gate y no se autorizó HOLDOUT.

## Hallazgo sobre trailing

El trailing `2R / activar 1R / distancia 1R` mejoró el EV frente al diagnóstico
de salida fija 1R:

- ES lidera breakout: `+0.06541R` por trade.
- Divergencia + reclaim: `+0.08542R` por trade.

Esto apoya conservar la gestión como componente, pero no demuestra edge de
entrada. La gestión no rescató ninguna familia después de costes.

## Lectura de falsificación

1. Perseguir el primer breakout NQ solo porque ES salió antes de su OR no
   ofrece una ventaja reproducible: el agregado es prácticamente cero y cambia
   de signo entre 2022 y 2023.
2. Desvanecer un sweep NQ únicamente porque ES no confirma y NQ vuelve al OR
   es peor: fue negativo en todos los años observados del estudio, también en
   el bloque descriptivo 2025–2026.
3. El siguiente experimento no debe elegir meses, dirección o rangos vistos
   para maquillar V1. Debe cambiar el mecanismo de entrada y congelarlo antes
   de medir:
   - aceptación fuera del OR seguida de retest;
   - reclaim fallido seguido de rebreak en dirección del sweep.

## Decisión

`LUCID150K-SNIPER-V1` queda cerrado como falsificación. No es apto para operar,
para simular una probabilidad Lucid ni para abrir datos reservados.

`INFORMATION_STATUS=LUCID150K_SNIPER_V1_DEV_FAIL_HOLDOUT_UNTOUCHED`
