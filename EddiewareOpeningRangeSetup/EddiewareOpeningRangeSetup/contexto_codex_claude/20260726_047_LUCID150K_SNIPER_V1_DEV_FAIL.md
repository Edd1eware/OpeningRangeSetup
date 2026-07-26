# 047 — LUCID150K-SNIPER-V1: fallo DEV, holdout intacto

Fecha: 2026-07-26  
Veredicto: **FAIL_NO_DOWNLOAD**

El estudio se ejecutó contra el prerregistro con SHA-256
`a173f38b9da683fcf170989c13e52d8e0d372fd08d368af018a5e5a17d8ea09a`.
Escaneó 1,028 fechas NQ/ES, produjo 424 registros entre todos los bloques y
terminó con cero errores.

## DEV 2022-04-25..2023-12-31

| Familia | n | EV neto | PF | Años positivos | Semestres positivos |
|---|---:|---:|---:|---:|---:|
| `S1_ES_LEADS_NQ_BREAKOUT` | 73 | -0.00374R | 0.9930 | 1/2 | 75% |
| `S2_NQ_DIVERGENCE_RECLAIM` | 86 | -0.08614R | 0.8528 | 0/2 | 0% |

Ninguna cumplió los gates congelados de EV, PF y estabilidad anual. No se
seleccionó familia y el HOLDOUT 2020-01-01..2022-04-22 no fue descargado ni
abierto.

## Hallazgo reutilizable

La gestión trailing mejoró el EV frente a target fijo 1R en ambas entradas:

- S1: `+0.06541R/trade`.
- S2: `+0.08542R/trade`.

No constituye edge por sí sola. El resultado importante es mecanístico:

- el breakout perseguido solo por liderazgo de ES es casi aleatorio y cambia
  de signo entre años;
- el fade de un reclaim sin confirmación ES es persistentemente negativo;
- el próximo estudio debe exigir aceptación/retest o explotar un reclaim
  fallido con rebreak, con reglas nuevas congeladas y sin filtros
  retrospectivos por mes, lado o volatilidad.

Artefactos fuente:

- `lucid150k_sniper_v1/output/DEV_RESULT.json`
  SHA-256 `0BF47D308A2E2FB5356DAC91737FB2F37ADF88779DA24D4AB6C45A74E05E40D8`.
- `lucid150k_sniper_v1/output/DEV_ALL_TRADES.csv`
  SHA-256 `CF4AE8564A34873B9C82CF69F31AE68EFC6BCFE860A02CB057454A4267EC7196`.

`INFORMATION_STATUS=LUCID150K_SNIPER_V1_DEV_FAIL_HOLDOUT_UNTOUCHED`
