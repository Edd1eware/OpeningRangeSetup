# 049 — V3: DST correcto elimina el supuesto edge UP

Fecha: 2026-07-26  
Veredicto: **FAIL_NO_DOWNLOAD**

Se regeneró el primer breakout alcista NQ con bracket 120/55, trailing,
`America/New_York`, invierno incluido y cierre EOD incluido. Prerregistro:
`915ec4c4365a49fd4575effa20066ad6b94fbff6c85caeda5a1db16d94725eb2`.

## Evidencia

| Gestión | n | EV | PF | Años positivos | Semestres positivos |
|---|---:|---:|---:|---:|---:|
| Trailing | 497 | +0.00578R | 1.0114 | 2/5 | 55.56% |
| Fixed diagnóstico | 497 | +0.02202R | 1.0313 | 2/5 | 55.56% |

EV trailing por año: 2022 `-0.134R`, 2023 `+0.049R`, 2024 `-0.018R`, 2025
`+0.158R`, 2026 `-0.123R`.

La frecuencia sí alcanza 9.75 trades/mes, pero no hay magnitud ni estabilidad.
El 68.1% del PnL positivo se concentra en un semestre. El hallazgo previo
UP>DOWN se apoyaba en una OR fija a 13:30 UTC que omitía invierno; ya no debe
presentarse como edge.

Holdout 2020–2022 intacto. Próxima vía: datos tempranos YM+RTY, ventana causal
reducida, para estudiar breadth/confirmación multi-instrumento sin multiplicar
entradas NQ.

SHA-256:

- resultado:
  `8F291F3557FEA22C9996A7A25430A7C422BD68BECDE97CF91A56FF5367F2A4D0`;
- trades:
  `D1738A37132925C8C58CF969F2B5C8895BC17490A3203435B1FDCDE5DE159AD0`.

`INFORMATION_STATUS=LUCID150K_SNIPER_V3_FAIL_DST_REMOVES_UP_EDGE`
