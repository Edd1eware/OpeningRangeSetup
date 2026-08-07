# Enmienda 003: validez del estado vigente de quote

Fecha: 2026-07-27

Estado: `BEFORE_CORRECTED_SMOKE_LABELS`

Tipo: fe de erratas de implementación e instrumentación. No cambia ningún
criterio científico.

## Intención ya congelada

El prerregistro V1 exige:

```text
reference <= tLB
depth age <= 250 ms
current spread in [1, 4] ticks
```

La implementación anterior reconstruía correctamente el libro, pero omitía
los estados inválidos de `QuoteSeries`. Si una quote válida era seguida por un
libro sin bid/ask o con spread fuera de 1–4 ticks, una actualización depth
reciente podía hacer que `reference_quote_at` devolviera la última quote válida
histórica como si siguiera vigente.

## Evidencia previa a la corrección

Test sintético:

```text
ask eliminado
estado vigente sin ask
resultado anterior = MID 100.5, depth_age_ms 0
resultado requerido = None
```

Auditoría independiente sobre las cinco sesiones
`TECHNICAL_DEVELOPMENT_SET`:

- 111/111 referencias anteriores reproducidas exactamente;
- 106/111 referencias con estado vigente válido;
- cinco falsas aceptaciones, 4.50%;
- no se recalcularon clases;
- no se abrió ninguna etiqueta no-smoke.

Artefacto de impacto:

```text
artifacts/quote_state_smoke_audit/manifest.json
```

## Corrección mecánica

`QuoteSeries` conservará transiciones explícitas entre:

```text
VALID
INVALID_NO_BOOK_OR_SPREAD
VALID
```

Reglas:

1. una referencia a `tLB` se rechaza si el último estado causal es inválido;
2. el feed más reciente sigue exigiéndose a no más de 250 ms;
3. el spread válido sigue siendo 1–4 ticks;
4. una trayectoria quote que cruce un intervalo inválido se rechaza;
5. al revalidarse el mismo precio/size anterior se emite una nueva transición
   válida;
6. se persisten `quote_ticks`, `depth_age_ms` y `quote_group_lag_ms` por LB.

No se interpola, no se rellena con futuro y no se modifica el orden de archivo
ni el watermark.

## Regla anti-puerta-trasera

Después de la corrección se repite la matriz V1 completa sobre las mismas cinco
sesiones técnicas y se toma mecánicamente el primer threshold que supere los
gates ya congelados:

```text
8 -> 12 -> 4 -> 16
```

Si deja de ser 8, se acata. No se conserva una definición por inercia y no se
elige por cantidad de positivos, AUC, accuracy, PnL, PF ni WR.

Target-only permanece bloqueado hasta que:

- el test sintético pase en verde;
- la auditoría V1 corregida termine;
- se emita el freeze V3 de alcance completo.

`INFORMATION_STATUS=AMENDMENT_003_CURRENT_QUOTE_VALIDITY_FROZEN`
