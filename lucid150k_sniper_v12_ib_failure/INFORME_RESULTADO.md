# LucidPro 150K — Sniper V12: fallo del IB30

Fecha: 2026-07-26

## Hipótesis preregistrada

Después de una ruptura aceptada del Initial Balance de 30 minutos (dos cierres),
un reclaim del nivel en no más de 300 segundos debía separar una ruptura fallida
y permitir un fade con stop estructural, objetivo de 2R y trailing desde +1R.

SHA-256 del preregistro:
`7a5edf16411bfbfc0d2bc3aee3796aa3b42f0f4b13e0053201954694a01e4576`.

## Resultado

- DEV 2022–2023: `n=284`, EV `-0.19409R`, PF `0.6773`, win rate `39.79%`.
- Años positivos: `0/2`; mitades positivas: `25%`.
- 2022: `-0.30761R`; 2023: `-0.12338R`.
- Frecuencia: `13.52` operaciones/mes.
- El trailing sólo mejoró `+0.00522R` frente a la salida fija.
- Stress visible 2025–2026: `n=233`, EV `-0.02021R`, PF `0.9611`.

La muestra es suficiente para rechazar esta formulación. No se abrió el
pseudo-holdout 2024 ni el holdout 2020–2022.

## Conclusión causal provisional

V11 mostró que continuar la ruptura del IB30 pierde; V12 muestra que invertirla
tras un reclaim simple también pierde. El cruce del nivel del IB, por sí solo,
no clasifica el régimen con utilidad operable. La siguiente familia debe usar
la geometría del impulso de apertura y su pullback, no otra variante del mismo
nivel.

## Integridad

- `RESULT.json`:
  `D6FF9CE5AEF2A0238D7A1AF0BC06606AB0E34B7D9FD4B6B18AA1FF9740E4FA62`
- `ALL_TRADES.csv`:
  `2458F8ACEA75EADB3CA2EC73C4E21540FB61F0985E18364A38CC207699DC5B93`

`INFORMATION_STATUS=LUCID150K_SNIPER_V12_FAIL`
