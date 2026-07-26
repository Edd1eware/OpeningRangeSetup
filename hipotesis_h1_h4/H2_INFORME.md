# H2 — Gate de régimen tendencial: RECHAZADA (2 de 5 gates)

Fecha: 2026-07-25 · Preregistro `f5fa1d4b…` + `ERRATA_H2_001.md`
Base usada: **ambas direcciones** (por regla de encadenamiento, H1 falló)

## Veredicto: FAIL — y el gate empeora, no mejora

| Gate | Umbral | Obtenido | |
|---|---|---:|---|
| G1 EV neto > 0 | > 0 | **−0.649** | FAIL |
| G2 PF > 1.15 | > 1.15 | **0.967** | FAIL |
| G3 Años EV>0 ≥ 2 | ≥ 2 de 3 | 2 de 3 | PASS |
| G4 Frecuencia ≥ 4/mes | ≥ 4 | 14.52 | PASS |
| G5 Supera baseline | > −0.577 | **−0.649** | FAIL |

## El resultado central

| FRESH | Trades | Trades/mes | WR % | PF | EV neto |
|---|---:|---:|---:|---:|---:|
| Sin gate | 402 | 18.27 | 39.30 | 0.970 | **−0.577** |
| Con gate de régimen | 305 | 14.52 | 40.00 | 0.967 | **−0.649** |

El gate descarta 97 trades y **empeora** el EV neto. Peor aún, mira 2024:

| Year | Sin gate | Con gate |
|---|---:|---:|
| 2024 | −6.407 | **−7.462** |
| 2025 | +3.296 | +3.000 |
| 2026 | +3.487 | +2.943 |

**El gate empeora los tres años.** En 2024 —el año que debía proteger— pierde
más. Retiene 76% de los trades, así que casi no filtra, y lo poco que filtra lo
filtra mal.

## Qué queda descartado

La afirmación de H2 era: *la tendencialidad de las sesiones previas anticipa
causalmente el régimen de chop*. **Es falsa** con esta definición.

Implicación real: el régimen de 2024 **no es autocorrelacionado** de la forma
asumida. No se anuncia en la tendencialidad reciente de las 20 sesiones previas.
Un detector de régimen basado en persistencia de tendencia no va a funcionar; si
2024 es detectable ex-ante, tendrá que ser por otra vía (macro, volatilidad
implícita, estructura de term, dispersión) — no por momentum de la propia serie.

Esto es informativo: cierra una familia entera de soluciones al problema de 2024,
que era el destructor universal del proyecto.

## Nota sobre la errata

La primera corrida dio `n=0` por un defecto (154 sesiones con `rng_60==0` →
`min_periods=20` dejaba todas las ventanas vacías). Se corrigió a
`min_periods=10` **antes de ver métrica alguna** de H2; `n=0` no contenía
información sobre la hipótesis. Documentado append-only en `ERRATA_H2_001.md`.

## Encadenamiento

H1 y H2 fallaron → la base superviviente para H4 sigue siendo **ambas
direcciones**, que tiene EV neto negativo. Se advierte de antemano: probar
sizing sobre una base de EV negativo es casi una conclusión matemática adelantada
—el sizing no crea edge donde no lo hay— pero se ejecuta según lo preregistrado
y se reporta honestamente.

`INFORMATION_STATUS=H2_REJECTED_REGIME_NOT_PREDICTIVE`
