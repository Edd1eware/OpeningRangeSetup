# Addendum H3-001 — H3 pasa a TESTEABLE, con exclusión obligatoria por sesgo

Fecha: 2026-07-25 · Append-only, escrito **antes** de ver ningún resultado de H3

## 1. Corrección de un error mío de conteo

En el informe previo declaré H3 `NO TESTEABLE` con "91 sesiones etiquetadas".
**Ese conteo estaba mal**: conté solo las sesiones **con** burst detectado, no las
sesiones **etiquetadas**. Una sesión replayed sin burst está etiquetada igual
(LB ausente) y es imprescindible como grupo de control.

Cobertura real, uniendo `run_state.json` de todas las carpetas de replay LB:

```text
sesiones replayed (etiquetadas) = 356
   con LB    = 209
   sin LB    = 147
FRESH (2024-26) etiquetadas = 285
```

Condición de viabilidad del preregistro: ≥300 etiquetadas y ≥100 en FRESH.
**356 ≥ 300 y 285 ≥ 100 → se cumple.** H3 pasa a TESTEABLE. No hace falta correr
ATAS: los datos ya existían.

## 2. Exclusión obligatoria de 2022-2024 por sesgo de selección

| Año | Replayed | Con LB | Sin LB | Tasa LB |
|---|---:|---:|---:|---:|
| 2022 | 34 | 32 | 2 | **94%** |
| 2023 | 37 | 34 | 3 | **92%** |
| 2024 | 29 | 25 | 4 | **86%** |
| 2025 | 165 | 78 | 87 | 47% |
| 2026 | 91 | 40 | 51 | 44% |

2022-2024 provienen del *pilot100 discovery*, que **seleccionó sesiones porque
tenían LB**. Su grupo de control es de 2-4 días: comparar ahí no mide nada.
2025-2026 son replay sistemático de todos los días de la ventana DST, con tasa LB
del 44-47% y control amplio.

Por tanto H3 se evalúa **solo sobre 2025-2026** (256 fechas). Esto no es
cherry-picking: es excluir una muestra sesgada por construcción. La decisión se
toma antes de calcular cualquier métrica de H3.

## 3. Consecuencia: esto es caracterización, no validación

Dentro de 2025-2026 **no hay era-split posible** (ambos son años favorables para
el baseline). Igual que en UPBIAS-V2 Parte A, un PASS aquí **no valida** el
filtro: solo indica que merece un forward. Se declara ahora para que no se
reinterprete después.

## 4. Especificación congelada

```text
universo   = 256 fechas replayed sistematicamente 2025-03-10 .. 2026-07-15,
             intersectadas con el dataset de PnL (termina 2026-07-01)
base       = ambas direcciones  (regla de encadenamiento original: H1 y H2 fallaron)
regla H3   = base AND dia_tiene_LB
comision   = 2.0 ticks
```

Gate (adaptado a que solo hay 2 años, se declara ahora):

| # | Criterio | Umbral |
|---|---|---|
| G1 | EV neto | > 0 |
| G2 | Profit Factor | > 1.15 |
| G3 | Años con EV neto > 0 | **2 de 2** |
| G4 | Frecuencia | ≥ 4 trades/mes |
| G5 | Supera al mismo universo sin filtro | EV neto mayor |

**Corte secundario declarado sin autoridad de veredicto:** se reportará también
el resultado sobre solo-UP, porque la base de ambas direcciones tiene EV negativo
y repetir el error de H4 sería inútil. Ese corte es **descriptivo**: no otorga
PASS ni cambia el veredicto, que lo decide únicamente la base preregistrada.

`INFORMATION_STATUS=H3_TESTABLE_ADDENDUM_BEFORE_RESULT`
