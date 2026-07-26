# Prerregistro LUCID150K-SNIPER-V12-IB-FAILURE

Fecha: 2026-07-26  
Estado: **CONGELADO ANTES DE MEDIR V12**

Hipótesis: la ruptura aceptada del IB30 tiene EV negativo; el edge puede estar
en el fallo confirmado que vuelve al Initial Balance.

```text
NQ 1s, NY
IB [09:30,10:00)
aceptación 10:00..11:00
reclaim máximo300s
última entrada11:05
exit15:55
```

Regla:

1. Primeros 2 cierres consecutivos fuera del IB por >=1 tick.
2. Congelar extremo desde el primer cierre de la secuencia hasta reclaim.
3. Reclaim:
   - UP break: primer `close<IB_high`;
   - DOWN: primer `close>IB_low`.
4. Entrada siguiente open +1 tick adverso, contra el breakout.
5. Stop extremo del movimiento +4 ticks.
6. Si riesgo<20, ampliar a20; si riesgo>80, excluir.
7. Target2R, trailing activa1R/distancia1R, BE neto, coste4t.
8. Máximo1/día, orden intrabar pesimista, FIXED_1R diagnóstico.

DEV 2022-04-25..2023-12-31:
`n>=80, >=4/mes, EV>0.10R, PF>1.30, 2/2 años+, >=60% semestres+,
trailing-fixed>=-0.05R`.

PSEUDO2024:
`n>=40, EV>0, PF>1.15, IC95 low>-0.08R`, 10k seed
`0xB38D50C2741EA69F`.

Solo PASS permite HOLDOUT. HOLDOUT:
`n>=80, EV>0, PF>1.20, >=2 años+, IC95 low>-0.05R`.

LucidPro150K: 9k target, MLL4.5k, DLL2.7k, 63 sesiones, 50k intentos,
budget1.2/1.5/1.8k, max6 NQ, Ppass>=50%, breach<=20%.

No cambiar IB, 2 cierres, 300s, stop, gestión, horarios, costes o gates.

`INFORMATION_STATUS=LUCID150K_SNIPER_V12_PREREGISTERED_NO_RESULT`
