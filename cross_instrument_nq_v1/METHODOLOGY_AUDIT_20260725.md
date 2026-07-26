# Auditoría metodológica — DST de Nueva York y reglas LucidPro

Fecha: 2026-07-25  
Estado: hallazgo factual previo a `CROSS-INSTRUMENT-NQ-V1`

## 1. Apertura del OR mal anclada

Los scripts históricos del OR declaran:

```text
OR_START = 13:30:00 UTC
OR_END   = 13:31:00 UTC
```

y describen esa ventana como `09:30-09:31 America/New_York`. La equivalencia
solo es cierta durante EDT (UTC-4). Durante EST (UTC-5), la apertura es
`14:30 UTC`.

Evidencia reproducible:

- un archivo NQ de enero de 2025 tiene índice UTC y comienza a `14:30 UTC`;
- contiene 60 barras en `14:30-14:31` y cero en `13:30-13:31`;
- `orb_trailing_pnl.csv` contiene 698 sesiones, concentradas entre marzo y
  noviembre, aunque `raw_dbn_2` contiene 1,029 fechas;
- por mes, el CSV previo tiene diciembre=0, enero=0, febrero=0 y noviembre=8.

Consecuencia: los informes que describen ese CSV como “2022-2026” midieron en
realidad la temporada EDT. Sus cálculos son reproducibles sobre ese subconjunto,
pero no representan el año completo. Las sesiones EST omitidas no se usarán
para ajustar reglas: serán un bloque de resultado no observado.

Corrección:

```text
convertir cada índice UTC a America/New_York
OR = 09:30:00 <= hora NY < 09:31:00
scan = hora NY >= 09:31:00
```

No se reemplazan silenciosamente los artefactos anteriores. Los resultados
corregidos viven en un directorio nuevo.

## 2. MLL de LucidPro mal simulado

Los Monte Carlo previos implementan:

```text
floor = peak_EOD - MLL
```

para toda la vida de la cuenta. En LucidPro 150k la regla vigente es:

```text
target                    = +9,000 USD
MLL                       = 4,500 USD
initial floor             = -4,500 USD relativo
initial trail balance     = +4,600 USD relativo
locked floor              = +100 USD relativo
official floor            = min(peak_EOD - 4,500, +100)
DLL                       = 2,700 USD, breach suave
max size                  = 10 NQ o 100 MNQ
expiration                = ninguna
```

Los simuladores anteriores también limitaron algunos intentos a 120 días. La
evaluación LucidPro no vence. Ambos supuestos reducen artificialmente
`P(pass)`.

Una comprobación diagnóstica, no confirmatoria, sobre el pool ya visto
2024-2026 de `fixed_60_60`, UP-only y 3 NQ dio:

```text
simulador anterior: P(pass) ~= 29.7%
regla de piso oficial: P(pass) ~= 36.8%
```

Este diagnóstico no valida el edge: el pool ya fue estudiado y además omite
EST. Solo demuestra que las probabilidades de pase anteriores deben retirarse.

## 3. Alcance

Se mantienen separados:

1. existencia y estabilidad del edge (EV, PF, años);
2. compatibilidad del edge con la geometría de LucidPro;
3. validación forward posterior a 2026-07-01.

Corregir el simulador puede rescatar la compatibilidad con la cuenta, pero no
convierte un patrón inestable en edge validado.

`INFORMATION_STATUS=DST_AND_LUCID_SIMULATION_DEFECTS_CONFIRMED`
