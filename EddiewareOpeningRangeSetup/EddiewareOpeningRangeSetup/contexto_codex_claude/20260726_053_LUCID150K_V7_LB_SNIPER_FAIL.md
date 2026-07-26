# 053 — V7 LB sniper recupera frecuencia, pierde estabilidad

Fecha: 2026-07-26  
Veredicto: **FAIL_NO_HOLDOUT**

V7 usó acceptance 4/5, stop20, target40, trailing20 y máximo dos episodios
independientes:

```text
DEV n=54, 2.57 trades/mes, EV +0.06296R, PF 1.1349
2022 +0.344R
2023 -0.179R
2025–2026 n=25, EV -0.208R, PF 0.6667
```

El trailing aporta `+0.15185R` frente a fixed40/20, pero no hay edge estable. El
positivo V5 no se transporta al ampliar cobertura; dependía de la selección por
midpoint/riesgo.

Siguiente estudio: complemento outcome-blind de V4 — primer breakout NQ como
líder mientras al menos dos de ES/YM/RTY siguen neutrales y ninguno está fuera
por el lado opuesto.

SHA-256 resultado
`0FDE99AFED0357C77EBFEEADA4BDE172B25A7138C7AA5EF07FDFE7D314583E26`.

`INFORMATION_STATUS=LUCID150K_SNIPER_V7_FAIL_LB_NOT_SUSTAINABLE`
