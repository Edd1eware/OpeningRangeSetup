# Resultado DEV — LUCID150K-SNIPER-V2

Fecha: 2026-07-26  
Prerregistro SHA-256:
`78467379fd13c27e7bed05b9932695d29bfc180ae625c572e0d7ccf75c19157f`  
Veredicto: **FAIL_NO_DOWNLOAD**

## Integridad

- 1,028 sesiones NQ/ES DST-aware.
- 450 operaciones entre todos los bloques observados.
- 0 errores.
- HOLDOUT 2020-01-01..2022-04-22 intacto.

## DEV

| Familia | n | EV | PF | EV 2022 | EV 2023 | Semestres + | PASS |
|---|---:|---:|---:|---:|---:|---:|---|
| Acceptance + retest | 95 | -0.04942R | 0.9128 | +0.17461R | -0.24270R | 50% | No |
| Reclaim fallido + cross-rebreak | 129 | -0.12575R | 0.7470 | -0.17667R | -0.09246R | 0% | No |

Ninguna familia cumple EV, PF ni estabilidad anual. La segunda además falla el
gate de gestión: el trailing resta `-0.12599R/trade` frente a `FIXED_1R`.

## Hallazgo de gestión

- Acceptance + retest: trailing menos fixed = `+0.08066R`.
- Failed reclaim + rebreak: trailing menos fixed = `-0.12599R`.

El trailing no es transportable entre entradas. Debe diseñarse como parte del
mecanismo de cada setup y no añadirse universalmente después.

## Siguiente vía

Los estudios anteriores encontraron que:

- UP supera DOWN en 8/8 gestiones;
- el bracket bruto 120/55 sin CatBoost fue positivo, pero todo ese cálculo usó
  13:30 UTC fijo y por ello está contaminado por el defecto DST.

La siguiente hipótesis legítima es regenerar **long-only, primer breakout UP,
bracket 120/55 con trailing** usando reloj NY correcto e incluyendo timeouts,
antes de considerar el holdout.

SHA-256:

- `DEV_RESULT.json`:
  `D968D13AF92E51CF3427CCAAE9836F10AB91C8D681905C7280F575F654DEA47C`.
- `ALL_TRADES.csv`:
  `EA338AAFA357A9460077603B7222DA3A86A3D057E390A1BD9412BFDB9115EC95`.

`INFORMATION_STATUS=LUCID150K_SNIPER_V2_DEV_FAIL_HOLDOUT_UNTOUCHED`
