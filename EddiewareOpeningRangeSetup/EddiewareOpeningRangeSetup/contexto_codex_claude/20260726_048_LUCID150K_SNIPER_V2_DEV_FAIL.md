# 048 — LUCID150K-SNIPER-V2: retest y rebreak fallan

Fecha: 2026-07-26  
Veredicto: **FAIL_NO_DOWNLOAD**

Prerregistro:
`78467379fd13c27e7bed05b9932695d29bfc180ae625c572e0d7ccf75c19157f`.
Ejecución DST-aware sobre 1,028 fechas NQ/ES, 450 operaciones totales y cero
errores.

## Resultado DEV

| Familia | n | EV neto | PF | Años positivos | Trailing vs fixed |
|---|---:|---:|---:|---:|---:|
| `A_CROSS_ACCEPTANCE_RETEST` | 95 | -0.04942R | 0.9128 | 1/2 | +0.08066R |
| `B_FAILED_RECLAIM_CROSS_REBREAK` | 129 | -0.12575R | 0.7470 | 0/2 | -0.12599R |

No se seleccionó candidata ni se abrió PSEUDO_VAL como gate. El holdout
2020-01-01..2022-04-22 permanece sin descargar.

## Hallazgo importante

El trailing ayuda al breakout/retest, pero destruye valor en el rebreak. Por
tanto, no es una capa universal: la regla de salida debe ser coherente con la
distribución de MFE/MAE y el mecanismo de entrada.

La siguiente vía separada será regenerar con DST correcto el fenómeno más
robusto previo: primer breakout OR alcista, bracket inicial 120/55
(`RR=2.18:1`) y trailing específico. Los resultados anteriores de esa familia
se calcularon con 13:30 UTC fijo, de modo que no son evidencia válida para
invierno.

Artefactos:

- `DEV_RESULT.json` SHA-256
  `D968D13AF92E51CF3427CCAAE9836F10AB91C8D681905C7280F575F654DEA47C`.
- `ALL_TRADES.csv` SHA-256
  `EA338AAFA357A9460077603B7222DA3A86A3D057E390A1BD9412BFDB9115EC95`.

`INFORMATION_STATUS=LUCID150K_SNIPER_V2_DEV_FAIL_HOLDOUT_UNTOUCHED`
