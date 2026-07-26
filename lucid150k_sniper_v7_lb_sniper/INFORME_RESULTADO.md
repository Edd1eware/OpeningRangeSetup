# Resultado — LUCID150K-SNIPER-V7-LB-SNIPER

Fecha: 2026-07-26  
Prerregistro:
`4c96e1b79ad3c48715d2574faae5e236589508f5dd7822878cf448191b4c1034`  
Veredicto: **FAIL_NO_HOLDOUT**

Con stop20/target40 y hasta dos episodios independientes:

| Bloque | n | EV | PF | Años + |
|---|---:|---:|---:|---:|
| DEV | 54 | +0.06296R | 1.1349 | 1/2 |
| 2025–2026 descriptivo | 25 | -0.20800R | 0.6667 | 0/2 |

DEV cambia de `+0.344R` en 2022 a `-0.179R` en 2023. La validación descriptiva
es negativa en 2025 y 2026. El trailing mejora `+0.15185R` contra fixed40/20,
pero no rescata la entrada.

Conclusión: el aparente edge V5 dependía de la selección estructural impuesta por
el midpoint/rango de riesgo; no se transporta al universo de aceptación con
stop sniper fijo.

SHA-256:

- resultado `0FDE99AFED0357C77EBFEEADA4BDE172B25A7138C7AA5EF07FDFE7D314583E26`;
- trades `6D1A2276CAD7628E00178F2C9C5D4C97970CC59B8A94FF6740B66E48FEDC82FE`.

`INFORMATION_STATUS=LUCID150K_SNIPER_V7_FAIL_LB_NOT_SUSTAINABLE`
