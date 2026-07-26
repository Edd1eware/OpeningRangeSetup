# 051 — V5 LB mechanism: señal prometedora, muestra insuficiente

Fecha: 2026-07-26  
Veredicto: **FAIL_NO_HOLDOUT**

V5 seleccionó el primer LB elegible del día, esperó cinco barras completas y
separó aceptación de reclaim. Excluyó 2024. Prerregistro:
`3887e468ff4147790eb03da30f99caa9f45c2f736a5883768b1ba748645f2f87`.

## DEV

| Familia | n | EV | PF | Años + | Resultado |
|---|---:|---:|---:|---:|---|
| Continuation acceptance | 16 | +0.30467R | 1.9175 | 2/2 | FAIL n<18 |
| Absorption reclaim | 4 | +0.36098R | 1.6423 | 1/2 | FAIL n/estabilidad |

Continuation cumple EV, PF, estabilidad anual/semestral y trailing, pero no el
tamaño mínimo sellado. En 2025–2026 solo aparecen 3 casos comparables. Absorción
tiene 10 casos posteriores, pero cambia de `-0.552R` en 2025 a `+1.549R` en
2026.

De 96 eventos iniciales, 59 quedaron fuera por riesgo estructural fuera de
20..80 ticks. No se relaja el rango después de ver el positivo.

Conclusión: cinco barras de aceptación son una pista útil para Liquidity Burst,
pero no hay frecuencia ni potencia suficiente para una cuenta LucidPro 150K en
63 sesiones. Holdout intacto.

SHA-256:

- resultado
  `23F2B38784E8D2AB8BFB0845918EA62C6BBE7FE8A47CB12EFB51E650018A437A`;
- trades
  `5BDD9C37E0F9FC6C0A995872FCAB8111E1CFED624A8261ABDBA85C8EF6150625`.

`INFORMATION_STATUS=LUCID150K_SNIPER_V5_FAIL_PROMISING_BUT_UNDERPOWERED`
