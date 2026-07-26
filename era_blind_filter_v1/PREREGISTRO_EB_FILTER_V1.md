# Preregistro — Filtro de participación por 3 condiciones era-blind (EB-V1)

Fecha: 2026-07-25
Autor: Claude Fable
Estado: **CONGELADO ANTES DE MEDIR**. Se hashea antes de ejecutar el test.

## 0. Advertencia de honestidad

Las tres condiciones que pasaron era-blind el 02-jul-2026 (`dentro-VA-previo`,
`exceso low`, `vol slope`) están registradas solo como una línea de memoria. Los
artefactos de aquel test (carpeta `Desktop\Codex_cotexto`) **ya no existen**, así
que NO puedo recuperar sus definiciones ni umbrales exactos.

Por tanto esto **NO es una re-corrida de un test aprobado**. Es un test nuevo,
preregistrado, de las mismas tres *familias* de condiciones, sobre el dataset que
sí tiene PnL real. El crédito de "ya pasó era-blind" NO se transfiere: este test
puede reprobar y eso sería un resultado válido.

## 1. Universo y regla de trade (congelados)

```text
dataset  = Documents\Indicador ATAS\outputs\orb_bigmove_1s\
           orb_features_labels_1s.csv  (698 sesiones, 2022-04-25 -> 2026-07-01)
           orb_trailing_pnl.csv        (PnL por sesión y configuración)
regla    = OR breakout con trailing 50/20/40  (columna trail_50_20_40)
comision = 2.0 ticks por trade  (misma constante que orb_regime_filter.py)
```

La regla de trade NO se optimiza. Se usa la configuración ya congelada. No se
prueban otras columnas de PnL.

Baseline conocido sin filtro (dato público del dataset, no es outcome del test):
EV bruto +1.23 ticks, con 2024 negativo. El test decide si el filtro mejora esto
en el periodo fresco.

## 2. Split era-blind (cronológico, sin solape)

```text
DEV   = 2022 + 2023            (n = 296)   -> SOLO para fijar umbrales
FRESH = 2024 + 2025 + 2026     (n = 402)   -> disparo único, nunca se mira antes
```

FRESH incluye deliberadamente 2024, el régimen de chop que mató otras líneas. No
se excluye ningún año por conveniencia.

## 3. Las tres condiciones (causales, conocidas antes de la entrada)

| # | Nombre | Definición operativa | Umbral |
|---|---|---|---|
| C1 | dentro-rango-previo | `dist_pdh < 0 AND dist_pdl > 0` (breakout dentro del rango del día previo) | Cero natural, sin ajuste |
| C2 | exceso low | `dist_pdl <= q25_DEV(dist_pdl)` (proximidad/sondeo del mínimo previo) | Percentil 25 calculado SOLO en DEV |
| C3 | vol slope | `vol_5 / vol_120 >= mediana_DEV` (volatilidad de corto expandiéndose vs largo) | Mediana calculada SOLO en DEV |

C1 usa un corte natural (cero), no ajustado. C2 y C3 usan un estadístico único y
preespecificado de DEV (p25 y mediana). **No se barren umbrales.** Un solo valor
por condición, elegido por regla, no por resultado.

Faltantes: si una condición no es computable (NaN), cuenta como **no cumplida**.
Sin imputación.

## 4. Regla de participación

```text
score_condiciones = C1 + C2 + C3        (entero 0..3)
PARTICIPAR  <=>  score_condiciones >= 2
```

Se elige "al menos 2 de 3" a priori para preservar frecuencia (doctrina del
usuario: frecuencia > runners). No se prueban las variantes >=1 ni >=3.

## 5. Gate de éxito (los CINCO deben cumplirse en FRESH)

| # | Criterio | Umbral |
|---|---|---|
| G1 | EV neto (post comisión) | > 0 |
| G2 | Profit Factor | > 1.15 |
| G3 | Retención de trades | >= 40% de FRESH |
| G4 | Años fresh con EV neto > 0 | >= 2 de 3 |
| G5 | Supera al baseline sin filtro en FRESH | EV_filtrado > EV_baseline |

Un solo fallo = **FAIL**. No hay segundo intento, no se relaja ningún umbral
post hoc, no se prueban combinaciones alternativas de condiciones y no se cambia
la regla de participación después de ver FRESH.

## 6. Reporte obligatorio

Tabla año × métrica con: year, trades, trades/mes, WR, R:R, PF, EV bruto, EV neto
(comisión 2 ticks), más fila TOTAL. Separado DEV y FRESH. Breakeven WR explícito.

## 7. Prohibiciones

No mirar FRESH antes de fijar umbrales. No añadir condiciones. No cambiar la
regla de trade ni la comisión. No excluir años. No repetir el test con otro
split. Si FAIL, se documenta y se cierra la línea.

`INFORMATION_STATUS=EB_FILTER_PREREGISTERED_NO_RESULT`
