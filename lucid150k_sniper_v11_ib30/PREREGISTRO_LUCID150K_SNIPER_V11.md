# Prerregistro LUCID150K-SNIPER-V11-IB30

Fecha: 2026-07-26  
Estado: **CONGELADO ANTES DE MEDIR V11**

Hipótesis: tras completar el Initial Balance de 30 minutos, dos cierres
consecutivos fuera del rango representan continuación menos ruidosa que OR1/OR5.

```text
NQ ohlcv-1s, America/New_York
IB30 [09:30,10:00)
scan 10:00..11:00
force exit15:55
```

Regla:

1. Primeros dos cierres consecutivos, separados exactamente 1 s:
   - LONG `close>=IB_high+1tick`;
   - SHORT `close<=IB_low-1tick`.
2. Entrada siguiente open +1 tick adverso.
3. Stop fijo60 ticks, target120 ticks.
4. Trailing activa+60, distancia60, stop mínimo entry+4 ticks.
5. Coste4 ticks, orden intrabar pesimista, máximo1 trade/día.
6. FIXED_1R diagnóstico no seleccionable. RR inicial2:1.

DEV 2022-04-25..2023-12-31, todos:

```text
n>=120
frecuencia>=6/mes
EV>+0.08R
PF>1.25
2/2 años positivos
>=60% semestres positivos
trailing-fixed>=-0.05R
```

PSEUDO2024:

```text
n>=60, EV>0, PF>1.15, IC95 low>-0.08R
10k seed0x7D19E4A630C25BF8
```

Solo PASS permite HOLDOUT. HOLDOUT:
`n>=120, EV>0, PF>1.15, >=2 años+, IC95 low>-0.05R`.

LucidPro150K: target9k, MLL4.5k EOD, DLL2.7k, floor+100, 63 sesiones, 50k
intentos, budget1.2/1.5/1.8k, max6 NQ, Ppass>=50%, breach<=20%.

No cambiar IB, 2 cierres, horario, stop, target, trailing, costes o gates.

`INFORMATION_STATUS=LUCID150K_SNIPER_V11_PREREGISTERED_NO_RESULT`
