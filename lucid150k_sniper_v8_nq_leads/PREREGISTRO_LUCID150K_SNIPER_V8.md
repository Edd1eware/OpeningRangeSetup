# Prerregistro LUCID150K-SNIPER-V8-NQ-LEADS

Fecha: 2026-07-26  
Estado: **CONGELADO ANTES DE MEDIR EL COMPLEMENTO V4**

## 0. Hipótesis

V4 falsificó la continuación con breadth 2/3. V8 prueba el complemento
outcome-blind: NQ puede ser el instrumento líder de price discovery. El primer
breakout NQ se opera solo cuando al menos dos de ES/YM/RTY siguen dentro de sus
OR y ninguno rompe por el lado contrario.

No es fade ni confirmación amplia.

## 1. Datos

```text
NQ, ES, YM, RTY ohlcv-1s
America/New_York
OR por instrumento [09:30,09:31)
scan NQ 09:31..10:00
force exit 15:55
ticks NQ=.25 ES=.25 YM=1 RTY=.10
```

Solo cierres cross-market estrictamente anteriores al segundo NQ.

```text
DEV 2022-04-25..2023-12-31
PSEUDO_VAL 2024
STRESS 2025..2026-06-30 descriptivo
HOLDOUT 2020-01-01..2022-04-22
```

## 2. Entrada `NQ_LEADS_NEUTRAL_BREADTH`

1. Primer toque NQ de `OR_high+1 tick` u `OR_low-1 tick`; ambos en el mismo
   segundo = excluir.
2. Para ES/YM/RTY en dirección del toque NQ:
   - same-side = close fuera por >=1 tick en el mismo lado;
   - opposite = close fuera por >=1 tick en el lado contrario;
   - neutral = cualquier otro close.
3. Exigir:
   - `opposite_count == 0`;
   - `neutral_count >= 2`.
4. Entrada NQ en dirección del breakout al límite +1 tick.
5. Stop = midpoint OR NQ.
6. `20 <= R <= 80` ticks.
7. Máximo una entrada diaria.

No se prueba otro conteo.

## 3. Gestión

```text
coste 4 ticks
target +2R
activar trailing +1R
stop mínimo entry+coste
trailing best-1R
```

Orden intrabar pesimista. `FIXED_1R` diagnóstico. RR inicial 2:1.

## 4. Gates DEV

Todos:

```text
n >=80
frecuencia >=4 trades/mes
EV >+0.08R
PF >1.25
2/2 años positivos
>=60% semestres positivos
trailing menos fixed >=-0.05R
```

## 5. PSEUDO_VAL

Todos:

```text
n >=40
EV >0
PF >1.15
IC95 EV límite inferior >-0.08R
10,000 réplicas seed 0x13F8C6A90D427EB5
```

Solo PASS permite completar/adquirir datos posteriores y HOLDOUT.

## 6. HOLDOUT y LucidPro 150K

HOLDOUT:

```text
n>=80
EV>0
PF>1.15
>=2 años positivos
ningún año <-0.05R
IC95 EV low>-0.05R
```

Lucid:

```text
target +USD9,000
MLL EOD4,500; floor min(peak-4,500,+100)
DLL2,700
63 sesiones
50,000 intentos
budget USD1,200/1,500/1,800 según equity
máximo6 NQ
P(pass<=63)>=50%
P(breach antes del pase)<=20%
mediana condicional<=63
```

## 7. Prohibiciones

No barrer neutral/same/opposite, instrumentos, OR, horario, lado, riesgo,
target, trailing, costes o gates. No mezclar resultados V4. No abrir HOLDOUT
antes de PASS.

`INFORMATION_STATUS=LUCID150K_SNIPER_V8_PREREGISTERED_NO_RESULT`
