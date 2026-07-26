# H3 — Liquidity Burst como filtro de día: NO TESTEABLE

Fecha: 2026-07-25 · Preregistro `f5fa1d4b…`

## Veredicto: NO TESTEABLE con los datos actuales

El preregistro fijó una condición de viabilidad **antes** de mirar nada:

```text
exigido:  >= 300 de 698 sesiones con etiqueta LB,  y  >= 100 en FRESH
obtenido: 91 sesiones totales,  25 en FRESH
```

| Año | Sesiones con etiqueta LB |
|---|---:|
| 2022 | 32 |
| 2023 | 34 |
| 2024 | 25 |
| 2025 | **0** |
| 2026 | **0** |
| **Total** | **91** |

Fuente: `burst_causal_timeline.csv` / `burst_events.csv`, rango 2022-04-05 →
2024-08-14. No existe etiquetado LB para 2025 ni 2026, que son precisamente los
dos años donde el baseline es positivo.

## Por qué no se fuerza el test

El preregistro dice explícitamente: *"NO se sustituye por un proxy inventado ni
se etiqueta a mano un subconjunto conveniente"*. Correr H3 con 25 sesiones fresh
—todas de 2024, el peor año— daría un resultado sin poder estadístico y sesgado
por régimen. Reportarlo como evidencia sería peor que no correrlo.

## Qué haría falta para testearla

Ejecutar el detector de Liquidity Burst (ya existe: `12_LiquidityBurstDetector.cs`
y la infraestructura de replay 20/20) sobre las ~600 sesiones faltantes,
especialmente 2025-2026. Es trabajo de cómputo, no de investigación: el detector
está construido y validado.

Hasta entonces H3 queda **abierta, no refutada**. Es la única de las cuatro que
no recibió una respuesta empírica, y sigue siendo plausible: la evidencia
disponible (LB precede A+ 5/5 días, 0 días A+ sin LB, n=9) apunta a que el LB
funciona como condición necesaria a nivel de día, que es exactamente lo que H3
propone.

`INFORMATION_STATUS=H3_NOT_TESTABLE_INSUFFICIENT_LABELS`
