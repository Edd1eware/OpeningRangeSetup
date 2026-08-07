# Tests sintéticos del target de régimen

Fecha: 2026-07-27

Comando:

```text
python -m pytest volatility_trigger/tests -q
```

Resultado global antes del freeze:

```text
20 passed
```

Casos específicos de régimen:

| Caso | Resultado |
|---|---|
| continuation BUY | PASS |
| continuation SELL | PASS |
| reversal tras LB BUY | PASS |
| reversal tras LB SELL | PASS |
| no expansion | PASS |
| bidireccional dentro de 250 ms | PASS / AMBIGUOUS |
| empate temporal exacto | PASS / AMBIGUOUS |
| expansión posterior a 5 s | PASS: no expansión a 5 s, expansión a 10 s |
| trade exactamente en `tLB` | PASS: excluido del outcome |
| espejo BUY/SELL | PASS: salida idéntica |

También permanecen PASS los tests previos de timestamps, causalidad, profiles,
outcomes, depth, quotes as-of y eficiencia.

No se usaron datos reales de régimen para corregir estos tests.
