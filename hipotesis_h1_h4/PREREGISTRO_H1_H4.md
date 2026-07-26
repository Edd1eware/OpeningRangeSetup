# Preregistro — Batería de hipótesis H1..H4 (era-blind)

Fecha: 2026-07-25
Autor: Claude Fable
Estado: **CONGELADO ANTES DE EJECUTAR NINGUNA**. Las cuatro se especifican ahora
para que ninguna se diseñe sabiendo el resultado de la anterior.

## 0. Universo y regla común

```text
dataset  = Documents\Indicador ATAS\outputs\orb_bigmove_1s\
           orb_features_labels_1s.csv + orb_trailing_pnl.csv   (698 sesiones)
periodo  = 2022-04-25 .. 2026-07-01
regla    = OR breakout, trailing 50/20/40  (columna trail_50_20_40)
comision = 2.0 ticks por trade
DEV      = 2022 + 2023   (n=296)   descriptivo / origen de umbrales
FRESH    = 2024 + 2025 + 2026 (n=402)  disparo único por hipótesis
```

Baseline conocido (ya publicado en `CIERRE_EB_FILTER_V1_FAIL.md`): ambas
direcciones da EV neto −0.77 total, −0.58 en FRESH.

## 1. Gate común de "CANDIDATA POTENCIAL"

Los cinco deben cumplirse **en FRESH**:

| # | Criterio | Umbral |
|---|---|---|
| G1 | EV neto (post comisión) | > 0 |
| G2 | Profit Factor | > 1.15 |
| G3 | Años fresh con EV neto > 0 | ≥ 2 de 3 |
| G4 | Frecuencia | ≥ 4 trades/mes |
| G5 | Supera el baseline ambas-direcciones en FRESH | EV neto > −0.577 |

PASS en los cinco = **candidata potencial**. Un solo fallo = rechazada, se pasa a
la siguiente hipótesis. No se relajan umbrales, no se reintenta, no se cambian
las definiciones después de ver resultados.

---

## H1 — Sesgo estructural alcista del follow-through

**Afirmación:** el edge no es predecir dirección, es no operar el lado que
sangra. Los breakouts UP del OR continúan; los DOWN fallan.

```text
regla H1 = trade solo cuando direction == "UP"
parametros libres = NINGUNO
```

Cero umbrales que ajustar. DEV es puramente descriptivo: no se usa para fijar
nada. La prueba es si sobrevive el holdout temporal.

**Declaración de contaminación:** el split UP/DOWN full-sample fue observado por
Claude el 2026-07-25 mientras verificaba la semántica del dataset (UP +4.73 /
DOWN −1.94 bruto). Por tanto H1 es una hipótesis *generada por observación*, no
independiente. Mitigación: al no tener parámetros libres, lo único que puede
hacer es sobrevivir o no FRESH. Se reporta el caveat en el informe final.

---

## H2 — Gate de régimen tendencial (resuelve 2024)

**Afirmación:** la regla es rentable en régimen tendencial y negativa en chop;
la tendencialidad de las sesiones previas lo anticipa causalmente.

```text
tendencialidad_t = media sobre las K sesiones PREVIAS de |net_60| / rng_60
K = 20                       (elección única y convencional, no barrida)
umbral = mediana de tendencialidad en DEV   (un solo estadístico)
regla H2 = base_superviviente AND tendencialidad_t >= umbral_DEV
```

`net_60` y `rng_60` ya existen en el dataset. La media se calcula sobre las K
sesiones anteriores con `shift(1)`: el día de hoy queda excluido (causal).

**base_superviviente**: si H1 pasó, H2 se aplica sobre "solo UP". Si H1 falló, se
aplica sobre ambas direcciones. Esta regla de encadenamiento se fija AHORA.

---

## H4 — El edge está en el sizing, no en la entrada

**Afirmación:** con entradas mediocres, la gestión de riesgo dinámica genera EV
en términos de payouts esperados aunque el EV por trade sea marginal.

```text
base = base_superviviente al llegar a H4
sizing dinamico = kill-switch base-4c ya validado
                  (reduce tamaño tras pérdidas, base 4 contratos)
simulacion = Monte Carlo, 10,000 cuentas, barajando trades de FRESH
reglas Lucid 150k = target +$9,000 | MaxLoss $4,500 EOD | DLL $2,700 soft
metrica = payouts esperados por cuenta y P(quema)
```

**Gate propio de H4** (sustituye al común, porque la métrica es distinta):

| # | Criterio | Umbral |
|---|---|---|
| H4-G1 | Payouts esperados por cuenta | > 0.5 |
| H4-G2 | P(quema antes del primer payout) | < 50% |
| H4-G3 | Supera al sizing fijo equivalente | payouts > fijo |

---

## H3 — Liquidity Burst como filtro de DÍA

**Afirmación:** el LB no dice hacia dónde, dice si el día vale la pena operar.

```text
regla H3 = base_superviviente AND dia_tiene_LB
```

**Condición de viabilidad previa (obligatoria):** se exige cobertura de etiquetas
LB en ≥ 300 de las 698 sesiones, con ≥ 100 en FRESH. Si no existe esa cobertura,
H3 se declara **NO TESTEABLE** con los datos actuales y se reporta como tal —
NO se sustituye por un proxy inventado ni se etiqueta a mano un subconjunto
conveniente.

---

## 2. Prohibiciones para toda la batería

No se barren umbrales. No se prueban otras columnas de PnL. No se cambia la
comisión. No se excluye 2024. No se re-splitea. No se añaden hipótesis después de
ver resultados. Cada hipótesis se abre una sola vez sobre FRESH.

`INFORMATION_STATUS=H1_H4_PREREGISTERED_NO_RESULT`
