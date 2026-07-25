# Calibración conjunta A/B V4

Estado: **PASS**

## Integridad

- Diseño SHA-256: `c1eb770c0d69b9d684fc60147a0cf9d9aa15fdd7d39eccb33e367f612c9a339c`
- Sesiones leídas: 98
- Pseudo-ventanas válidas: 3533
- No se leyeron predictores ni outcomes terminales.
- No se descargaron datos.

## Umbrales congelados

- T_push/T_ret: 14.000000 ticks
- T_ext: 33.000000 ticks
- T_dwA: 0.671530336 s
- T_dwB: 0.453560071 s
- Soporte dwell A: 1819 ventanas
- Soporte dwell B: 355 ventanas

## Gates

- `design_hash_match`: PASS
- `session_count_98`: PASS
- `all_sessions_min_10_windows`: PASS
- `aggregate_min_1000_windows`: PASS
- `dwell_B_min_100_crossing_windows`: PASS
- `dwell_A_min_100_crossing_windows`: PASS
- `positive_price_thresholds`: PASS
- `positive_dwell_thresholds`: PASS
- `all_used_events_closed`: PASS
- `all_used_events_single_timestamp`: PASS
- `zero_maybe_bad_book_records`: PASS
- `zero_sequence_regressions`: PASS
- `deterministic_double_decode_3_sessions`: PASS

## Diagnóstico no vinculante sin 08:29–08:30 CT

- Ventanas: 2357
- P50 max|d|: 18.0
- P90 max|d|: 38.0

## Siguiente paso

Cotizar el tape postdecisión uniforme de 5.1 s para las 98 sesiones.
