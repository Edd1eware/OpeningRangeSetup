# UPBIAS-V2 Parte A — FAIL (4 de 7), pero con un positivo fuerte

Fecha: 2026-07-25 · Preregistro `80d219ba…` · Caracterización, **no validación**

## Veredicto: FAIL → no se pasa a la Parte B forward

| Check | Resultado | |
|---|---|---|
| A1-C1 UP > DOWN en ≥7 de 8 configs | **8 de 8** | PASS |
| A1-C2 UP positivo en ≥6 de 8 configs | **7 de 8** | PASS |
| A2-C1 ≥60% ventanas positivas | 66.7% (6 de 9) | PASS |
| A2-C2 ninguna ventana >50% del PnL | **71.2%** | **FAIL** |
| A3-C1 payouts esperados >0.5 | **0.381** | **FAIL** |
| A3-C2 quema sin payout <50% | **72.1%** | **FAIL** |
| A3-C3 dinámico > fijo | 0.3809 vs 0.3700 | PASS |

## A1 — El sesgo es REAL y robusto (resultado fuerte)

**UP supera a DOWN en las 8 configuraciones de gestión, sin excepción.** DOWN
pierde entre −4.58 y −5.00 ticks netos en todas; UP es positivo en 7 de 8.

| Config | EV neto UP | EV neto DOWN |
|---|---:|---:|
| trail_50_20_40 | +2.14 | −4.75 |
| fixed_60_60 | +1.98 | −4.95 |
| fixed_60_30 | +1.89 | −4.71 |
| trail_60_30_50 | −0.26 | −4.58 |

La asimetría **no es artefacto del trailing**: es una propiedad del mercado. Este
es el hallazgo más sólido que ha producido el proyecto.

## A2 — Pero el beneficio está concentrado

| Ventana | n | EV neto | PnL total |
|---|---:|---:|---:|
| 2022-H1 | 26 | +6.19 | +161 |
| 2022-H2 | 49 | −5.69 | −279 |
| 2023-H1 | 37 | +6.08 | +225 |
| 2023-H2 | 43 | +8.81 | +379 |
| 2024-H1 | 28 | +8.07 | +226 |
| 2024-H2 | 36 | −15.17 | **−546** |
| 2025-H1 | 44 | +14.68 | **+646** |
| 2025-H2 | 32 | −7.84 | −251 |
| 2026-H1 | 37 | +9.35 | +346 |

**Un solo semestre (2025-H1) aporta el 71% del PnL total.** Y hay tres semestres
con pérdidas fuertes. 6 de 9 positivos suena bien hasta que se ve que el
resultado depende de un tramo.

## A3 — La respuesta que H4 nunca pudo dar

Ahora sí sobre base **positiva** (pool EV neto +2.38, n=177):

| | Payouts esperados | P(quema) | P(quema sin payout) |
|---|---:|---:|---:|
| Dinámico | 0.3809 | 99.85% | 72.1% |
| Fijo | 0.3700 | 99.97% | 72.9% |

**El sizing dinámico sí gana al fijo sobre base positiva** — pero por 2.9%, no
por el +32% registrado en el resultado previo. Ese +32% se midió en otro
contexto y no se reproduce aquí.

Lo grave es lo otro: **con un edge de +2.38 ticks/trade, el 72% de las cuentas se
quema sin cobrar un solo payout** bajo reglas Lucid 150k.

## El diagnóstico real

El problema **no es que no haya edge**. El edge existe (A1: 8 de 8) y es
positivo. El problema es de **magnitud frente a las reglas de la cuenta**:

```text
EV +2.38 ticks x $5 x 4 contratos = ~$47.6 por día esperado
target $9,000  ->  ~189 días para el primer payout
MaxLoss $4,500 trailing = 225 ticks de drawdown con 4 contratos
```

Con ~1 trade/día y esa varianza, tocar 225 ticks de drawdown antes de acumular
$9,000 es lo que ocurre casi siempre. El edge es real pero **demasiado pequeño
para este vehículo a esta frecuencia**.

## Qué NO hago ahora

No paso a la Parte B (el preregistro lo prohíbe con un solo fallo). No busco la
configuración, el sizing ni el número de contratos que haga pasar el MC: eso
sería minar el mismo dataset por cuarta vez hoy. La restricción es estructural,
no un parámetro por afinar.

## Lo que esto deja establecido

1. La asimetría UP/DOWN en el breakout del OR es **real y robusta a la gestión**.
2. Es **temporalmente concentrada**: depende de tramos.
3. A esta frecuencia y con estas reglas de cuenta, **no alcanza para farmear
   payouts**. Se necesita más edge por trade, más trades por día, o reglas de
   cuenta distintas — no otro trailing.

`INFORMATION_STATUS=UPBIAS_V2_PARTE_A_FAIL_EDGE_REAL_PERO_INSUFICIENTE`
