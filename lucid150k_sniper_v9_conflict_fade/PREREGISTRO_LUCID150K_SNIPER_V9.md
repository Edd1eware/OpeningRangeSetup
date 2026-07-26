# Prerregistro LUCID150K-SNIPER-V9-CONFLICT-FADE

Fecha: 2026-07-26  
Estado: **CONGELADO ANTES DE MEDIR V9**

## Hipótesis

Un breakout NQ contra al menos dos índices que ya aceptan el lado opuesto puede
ser un error relativo, pero el fade solo se activa cuando NQ confirma el fallo
con reclaim dentro del OR en 15 segundos.

## Regla

```text
NQ/ES/YM/RTY ohlcv-1s, America/New_York
OR [09:30,09:31)
scan 09:31..10:00
```

1. Primer toque NQ `OR_high+1t` o `OR_low-1t`; ambos = excluir.
2. Usar cierres ES/YM/RTY estrictamente anteriores.
3. `opposite`:
   - breakout NQ UP: instrumento `close <= OR_low-1 tick propio`;
   - breakout NQ DOWN: instrumento `close >= OR_high+1 tick propio`.
4. Exigir `opposite_count >=2`.
5. Dentro de 15 s:
   - UP: primer NQ `close < OR_high`;
   - DOWN: primer NQ `close > OR_low`.
6. Entrada en la barra siguiente, 1 tick adverso, contra el breakout.
7. Stop = extremo del sweep hasta reclaim +2 ticks.
8. Si riesgo <20, ampliar a 20; si >80, excluir.
9. Máximo un trade/día.

Gestión: target2R, trailing activa1R/distancia1R, coste4t, orden pesimista,
FIXED_1R diagnóstico. RR inicial2:1.

## Bloques y gates

DEV 2022-04-25..2023-12-31, todos:

```text
n>=25
frecuencia>=1.2/mes
EV>+0.15R
PF>1.40
2/2 años positivos
>=60% semestres positivos
trailing-fixed>=-0.05R
```

PSEUDO 2024, todos:

```text
n>=15
frecuencia>=1.2/mes
EV>0
PF>1.15
IC95 low>-0.10R, 10k, seed 0xA51F7C309E2648BD
```

Solo PASS permite completar PSEUDO/HOLDOUT.

HOLDOUT 2020..2022-04-22:

```text
n>=30, EV>0, PF>1.20, >=2 años positivos, IC95 low>-0.05R
```

LucidPro 150K: target9k, MLL4.5k EOD, DLL2.7k, floor lock+100, 63 sesiones,
50k intentos, budget1.2k/1.5k/1.8k, max6 NQ; Ppass>=50%, breach<=20%.

No cambiar conteo2, reclaim15s, stop, gestión, reloj, instrumentos o gates. No
abrir HOLDOUT antes de PASS.

`INFORMATION_STATUS=LUCID150K_SNIPER_V9_PREREGISTERED_NO_RESULT`
