# Resultado — LUCID150K-SNIPER-V3

Fecha: 2026-07-26  
Prerregistro:
`915ec4c4365a49fd4575effa20066ad6b94fbff6c85caeda5a1db16d94725eb2`  
Veredicto: **FAIL_NO_DOWNLOAD**

## Resultado DST-aware 2022-04-25..2026-06-30

| Gestión | n | EV neto | PF | Años + | Semestres + |
|---|---:|---:|---:|---:|---:|
| Trailing 120/55 | 497 | +0.00578R | 1.0114 | 2/5 | 55.56% |
| Fixed 120/55 diagnóstico | 497 | +0.02202R | 1.0313 | 2/5 | 55.56% |

Frecuencia: 9.745 trades/mes. El trailing resta `-0.01624R`, dentro de su gate,
pero la entrada incumple EV, PF, estabilidad anual, estabilidad semestral y
concentración. El semestre positivo principal concentra 68.1% del PnL positivo.

EV anual trailing:

```text
2022 -0.13414R
2023 +0.04901R
2024 -0.01818R
2025 +0.15837R
2026 -0.12280R
```

## Conclusión

El supuesto sesgo alcista del primer ORB no sobrevive al reloj
`America/New_York`, a incluir invierno y a contabilizar timeouts. El resultado
previo basado en 13:30 UTC fijo no es una evidencia válida de edge sostenible.
No se descarga el holdout.

Artefactos:

- `DEV_RESULT.json` SHA-256
  `8F291F3557FEA22C9996A7A25430A7C422BD68BECDE97CF91A56FF5367F2A4D0`.
- `DEV_TRADES.csv` SHA-256
  `D1738A37132925C8C58CF969F2B5C8895BC17490A3203435B1FDCDE5DE159AD0`.

`INFORMATION_STATUS=LUCID150K_SNIPER_V3_FAIL_DST_REMOVES_UP_EDGE`
