# Preregistro LUCID100K-V1 — pasar la evaluación con RR 1:1

Fecha: 2026-07-25
Autor: Claude Fable
Estado: **CONGELADO ANTES DE MEDIR**

## 0. Objetivo y por qué la métrica cambia

Goal del usuario: **pasar una evaluación Lucid 100k con RR mínimo 1:1**.

```text
Lucid 100k:  profit target = $6,000 | MLL trailing = $3,000 (EOD) | NQ $5/tick
             (fuente: 07_strategy_lucid_report.py:6)
```

Pasar una evaluación **no es** farmear payouts. Se pasa **una vez**; quemarse
solo cuesta el intento. Por eso la métrica primaria es **P(pasar) por intento**,
no payouts esperados ni EV a 250 días.

## 1. Regla congelada (cumple RR 1:1 por construcción)

```text
entrada  = primer breakout del OR 09:30-09:31, SOLO direccion UP,
           al nivel del OR (primer cruce del dia)
gestion  = bracket FIJO  TP = 60 ticks / SL = 60 ticks   -> RR exactamente 1:1
comision = 2.0 ticks
tamano   = 2 contratos (tamano congelado para 100k en el proyecto)
fuente   = columna fixed_60_60 de orb_trailing_pnl.csv (ya calculada)
```

Breakeven WR con comisión: `62/120 = 51.67%`.

**Cero parámetros libres.** No hay umbral que ajustar: la dirección (UP) y el
bracket (60/60) están fijados por la restricción del goal, no elegidos por
resultado.

## 2. Split

```text
DEV   = 2022 + 2023   -> descriptivo (no se ajusta nada)
FRESH = 2024 + 2025 + 2026   -> disparo unico
```

## 3. Simulación de la evaluación (métrica primaria)

Monte Carlo, 10,000 intentos independientes, seed `0x22f9cadf098b1625`:

```text
capital inicial   = 0 (relativo)
objetivo          = +$6,000   -> PASA
limite            = MLL trailing $3,000 desde el pico -> QUEMA
tamano            = 2 contratos fijos (1 tick = $10)
trades            = muestreados con reemplazo del pool FRESH filtrado,
                    1 por dia habil, maximo 120 dias por intento
```

Se reporta: `P(pass)`, `P(burn)`, `P(timeout)`, y días medianos hasta pasar.

## 4. Gate (los cuatro, sobre FRESH)

| # | Criterio | Umbral |
|---|---|---|
| G1 | EV neto por trade | > 0 |
| G2 | WR | > 51.67% (breakeven) |
| G3 | **P(pasar) por intento** | **≥ 30%** |
| G4 | Años con EV neto > 0 | ≥ 2 de 3 |

G3 en 30%: con ~3 intentos esperados se pasa con alta probabilidad, lo que hace
la evaluación económicamente razonable frente al fee. Es el criterio primario;
G1/G2/G4 garantizan que el P(pass) venga de edge y no de varianza afortunada.

## 5. Prohibiciones

No se barren TP/SL. No se cambia la dirección. No se cambia el número de
contratos para hacer pasar el MC. No se excluye ningún año. No se añade filtro
alguno. Un fallo = rechazada y se documenta.

`INFORMATION_STATUS=LUCID100K_V1_PREREGISTERED_NO_RESULT`
