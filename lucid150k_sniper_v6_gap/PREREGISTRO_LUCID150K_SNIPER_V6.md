# Prerregistro LUCID150K-SNIPER-V6-GAP

Fecha: 2026-07-26  
Orden: ejecutar solo si V4 y V5 no llegan a HOLDOUT  
Estado: **CONGELADO ANTES DE CALCULAR OUTCOMES V6**

## 0. Hipótesis

El ORB indiscriminado no tiene edge. V6 prueba una población distinta:
`gap-and-go`. Un gap grande respecto al rango de la sesión anterior, que sigue
íntegramente abierto durante el primer minuto RTH, representa nueva información
y puede dar continuación al romper el OR en dirección del gap.

No usa Liquidity Burst ni confirmación cross-market.

## 1. Datos y reloj

```text
NQ.c.0 ohlcv-1s
timezone = America/New_York
sesión previa RTH = 09:30:00..15:59:59
OR actual = [09:30:00,09:31:00)
scan = 09:31:00..10:00:00
force exit = 15:55:00
```

Por fecha actual:

```text
prev_close = último close disponible de la sesión NQ anterior
prev_range = prev_high - prev_low de esa sesión
current_open = open de la primera barra >=09:30
gap = current_open - prev_close
```

Se exige `prev_range > 0`.

Bloques:

```text
DEV = 2022-04-26..2023-12-31
PSEUDO_VAL = 2024
STRESS_SEEN = 2025..2026-06-30, descriptivo
HOLDOUT = 2020-01-01..2022-04-22, cerrado
```

## 2. Entrada — `NORMALIZED_GAP_AND_GO`

1. Gap significativo:
   `abs(gap) >= 0.25 * prev_range`.
2. Gap UP:
   - todo el OR actual permanece sobre `prev_close`:
     `OR_low > prev_close`;
   - el primer toque de un límite OR después de 09:31 debe ser
     `OR_high + 1 tick`;
   - entrada LONG en ese nivel.
3. Gap DOWN:
   - todo el OR actual permanece bajo `prev_close`:
     `OR_high < prev_close`;
   - el primer toque debe ser `OR_low - 1 tick`;
   - entrada SHORT.
4. Ambos límites tocados en el mismo segundo = excluir.
5. Si el límite contrario se toca primero = invalidar.
6. Stop inicial = midpoint del OR actual.
7. Operar solo si `20 <= R <= 80` ticks.
8. Máximo una operación al día.

No se prueban otros umbrales de gap ni fill parcial.

## 3. Gestión

```text
coste = 4 ticks round-trip
target duro = +2R
activar trailing = +1R
stop mínimo al activar = entry + coste (break-even neto)
trailing = mejor extremo favorable - 1R
```

Orden OHLCV-1s pesimista. `FIXED_1R` diagnóstico no seleccionable. RR inicial
2:1.

## 4. Gates DEV

Todos:

```text
n >= 40
frecuencia >= 2 trades/mes calendario
EV neto > +0.15R
PF > 1.35
2/2 años con EV > 0
>=75% semestres con EV > 0
trailing menos FIXED_1R >= -0.05R
```

## 5. PSEUDO_VAL

Todos:

```text
n >= 20
EV > 0
PF > 1.15
bootstrap IC95 EV, límite inferior > -0.10R
10,000 réplicas, seed 0x61D4A8C3207FEB95
```

Solo PASS DEV + PSEUDO_VAL autoriza HOLDOUT.

## 6. HOLDOUT y LucidPro 150K

HOLDOUT, todos:

```text
n >= 40
EV > 0
PF > 1.15
>=2 años positivos
ningún año < -0.05R
bootstrap IC95 EV, límite inferior > -0.05R
```

Simulación:

```text
target +USD 9,000
MLL EOD USD 4,500
floor min(peak_EOD - 4,500,+100)
DLL USD 2,700 soft
63 sesiones máximo
50,000 intentos
budget USD 1,200 / 1,500 / 1,800 según equity
máximo 6 NQ
```

Gates:

```text
P(pass <=63) >=50%
P(breach antes del pase) <=20%
mediana condicional <=63 sesiones
```

## 7. Prohibiciones

No cambiar 0.25, horarios, lado, OR, stop, target, trailing, costes, bloques,
filtros o gates. No excluir gaps de noticias ni meses. No abrir HOLDOUT si
falta un gate. No reutilizar HOLDOUT para ajustar una variante.

PASS = candidata a forward, no garantía ni autorización de operación real.

`INFORMATION_STATUS=LUCID150K_SNIPER_V6_PREREGISTERED_NO_RESULT`
