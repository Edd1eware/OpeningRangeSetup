# H4 — Sizing dinámico: RECHAZADA (0 de 3 gates) — y el test fue estructuralmente inútil

Fecha: 2026-07-25 · Preregistro `f5fa1d4b…`
Base usada: **ambas direcciones** (forzada por encadenamiento: H1 y H2 fallaron)

## Veredicto: FAIL

| Gate | Umbral | Obtenido | |
|---|---|---:|---|
| H4-G1 payouts esperados > 0.5 | > 0.5 | **0.189** | FAIL |
| H4-G2 P(quema sin payout) < 50% | < 50% | **84.1%** | FAIL |
| H4-G3 supera al sizing fijo | > fijo | 0.189 vs **0.195** | FAIL |

Monte Carlo: 10,000 cuentas, reglas Lucid 150k (target $9,000, MaxLoss $4,500,
DLL soft $2,700), base 4 contratos, pool = 402 trades FRESH barajados.

| | Payouts esperados | P(quema) | P(quema sin payout) |
|---|---:|---:|---:|
| Kill-switch dinámico | 0.189 | 99.96% | 84.1% |
| Sizing fijo | 0.195 | 99.99% | 83.9% |

## El punto importante: este test no midió lo que debía

El pool tiene **EV neto = −0.577 ticks**. Sobre una base de EV negativo, el
sizing no puede generar valor: es aritmética, no un hallazgo. Reducir tamaño tras
pérdidas solo baja la exposición a un proceso perdedor; la diferencia entre
dinámico y fijo (0.189 vs 0.195) es ruido.

**Esto es una falla de MI preregistro, y la reconozco.** La regla de
encadenamiento que escribí —"si las anteriores fallan, H4 usa ambas
direcciones"— mandó H4 a probarse sobre una base perdedora, donde el resultado
estaba decidido de antemano. El test se ejecutó como estaba especificado y por
eso se reporta FAIL, pero no informa sobre la hipótesis real.

## Lo que NO se puede concluir

**No se concluye que el sizing dinámico sea inútil.** El kill-switch base-4c fue
validado antes con +$19,780 y +32% sobre fijo-2c, presumiblemente sobre una base
de EV positivo. Aquí se probó sobre EV −0.577. Los dos resultados no se
contradicen: describen contextos distintos.

La pregunta real —*¿aporta el sizing dinámico sobre una base de EV positivo, como
solo-UP (+2.38 neto) o ATRAPADOS?*— **queda sin probar**. No la corro ahora
cambiando la base: eso sería post hoc y violaría el preregistro. Requiere un
preregistro nuevo.

## Dato colateral relevante

Con este baseline, **99.96% de las cuentas se queman y 84% nunca cobran un
payout**. Es la cuantificación directa de por qué no se debe fondear sobre este
sistema: no es cuestión de mala racha, es el resultado esperado.

`INFORMATION_STATUS=H4_REJECTED_UNINFORMATIVE_BASE`
