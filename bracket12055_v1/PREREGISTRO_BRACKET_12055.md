# Preregistro BRACKET-120/55-V1 — bracket fijo sin filtro

Fecha: 2026-07-25
Autor: Claude Fable
Estado: **CONGELADO ANTES DE MEDIR NADA NUEVO**

## 0. Qué está contaminado y qué no

El bracket fijo 120/55 sin filtro apareció como línea de comparación obligatoria
en `orcb_v2\ORCB_V2_INFORME.md`. **Ya vi su resultado en FRESH 2024-26**:

```text
n=402  18.27 trades/mes  WR 34.83%  PF 1.106  EV neto +3.945
```

Por tanto **FRESH está quemado para este estudio**: no puede usarse como
confirmación en ningún gate. Se reporta solo como contexto conocido.

Lo que **no** he mirado nunca para esta configuración: **DEV 2022-2023 sin
filtro**. En OR-CB-V2, DEV se usó para entrenar el modelo, pero jamás se reportó
el desempeño del bracket 120/55 crudo en ese periodo. Es material limpio para
esta pregunta.

Estructura, igual que en UPBIAS-V2:

| Parte | Qué hace | Qué NO hace |
|---|---|---|
| **A — Caracterización** | Mide fragilidad con datos disponibles | **No valida.** No promueve nada |
| **B — Validación forward** | Decide de verdad, con datos que aún no existen | Requiere esperar |

## 1. Regla congelada

```text
entrada  = primer breakout del OR 09:30-09:31, AMBAS direcciones,
           al nivel del OR, desde 13:31:00 UTC
gestion  = bracket FIJO  TP = 120 ticks  /  SL = 55 ticks
           regla barra a barra pesimista: si en la misma barra se tocan
           ambos, gana el SL
comision = 2.0 ticks
etiqueta = ORCB_V2_LABELS.csv (y120), ya generada y hasheada
```

Breakeven WR = `55/(120+55) = 31.43%`. Sin filtros, sin selección direccional,
sin condiciones adicionales. Cero parámetros libres.

## 2. PARTE A — Caracterización (NO validatoria)

### A1 — ¿Funciona en el periodo que no he mirado? (DEV 2022-2023)

```text
A1-C1: EV neto > 0
A1-C2: PF > 1.15
```

### A2 — ¿Se sostiene en el tiempo o vive de un tramo?

Ventanas semestrales sobre todo el periodo 2022-2026 (≈9 ventanas):

```text
A2-C1: >= 60% de ventanas con EV neto > 0
A2-C2: ninguna ventana concentra > 50% del PnL total
```

### A3 — ¿Sirve para el objetivo real? (MC Lucid 150k)

Monte Carlo 10,000 cuentas, target $9,000, MaxLoss $4,500, base 4 contratos,
kill-switch dinámico, seed `0x22f9cadf098b1625`, pool = **todo el periodo**
(2022-2026, porque FRESH ya está quemado y aislarlo no aporta).

```text
A3-C1: payouts esperados > 0.5
A3-C2: P(quema antes del primer payout) < 50%
```

### Criterio de la Parte A

PASS = **todos** los criterios de A1, A2 y A3. Un fallo → frágil, no se pasa a la
Parte B. **PASS no significa validado**: significa que merece gastarse un
forward.

## 3. PARTE B — Validación forward (hasheada ahora)

```text
regla    = la de la seccion 1, sin cambios
inicio   = primera sesion posterior a 2026-07-01 con dato disponible
n minimo = 40 trades
```

| # | Criterio | Umbral |
|---|---|---|
| B1 | EV neto | > 0 |
| B2 | Profit Factor | > 1.15 |
| B3 | Meses con EV neto > 0 | ≥ 1 de 2 |
| B4 | Frecuencia | ≥ 10 trades/mes |

## 4. Prohibiciones

No se barren TP ni SL. No se añade filtro direccional ni de ningún tipo. No se
excluye ningún año ni ventana. No se cambia el número de contratos para hacer
pasar el MC. FRESH 2024-26 no otorga PASS en ningún criterio. Si la Parte A
falla, se cierra y se documenta.

`INFORMATION_STATUS=BRACKET12055_PREREGISTERED_NO_RESULT`
