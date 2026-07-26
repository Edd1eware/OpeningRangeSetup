# OR-CB-V2 — El filtro CatBoost no se valida. OR-CB sigue bloqueado.

Fecha: 2026-07-25 · Preregistro `cdfa8bbf…` · Disparo único sobre FRESH

## 1. Veredicto: FAIL (2 de 4 gates)

| Gate | Umbral | Obtenido | |
|---|---|---:|---|
| C1 EV neto > 0 | > 0 | +1.333 | PASS |
| C2 PF > 1.15 | > 1.15 | **1.035** | **FAIL** |
| C3 Años EV>0 ≥ 2 | ≥ 2 de 3 | 2 de 3 | PASS |
| C4 Frecuencia ≥ 3/mes | ≥ 3 | **2.29** | **FAIL** |

## 2. El hallazgo diagnóstico: el threshold nunca calificó

La regla preregistrada era *"el menor p tal que la precisión en validación
interna ≥ 0.40"*. **Ningún candidato lo alcanzó**, así que entró el fallback
declarado (`thr = 0.50`) y `precision_inner_en_thr = None`.

Con una tasa base de ~35%, el modelo **no logró llevar la precisión a 40% ni
siquiera en validación interna** — es decir, ya fallaba dentro de DEV, antes de
tocar FRESH. Eso, por sí solo, dice que la señal no está.

## 3. El filtro EMPEORA el baseline

| FRESH 2024-26 | Trades | Trades/mes | WR % | PF | EV neto |
|---|---:|---:|---:|---:|---:|
| Sin filtro (bracket 120/55) | 402 | 18.27 | 34.83 | 1.106 | **+3.945** |
| **Con filtro CatBoost** | 39 | 2.29 | 33.33 | 1.035 | **+1.333** |

Aplicar el modelo recorta el EV a un tercio, baja el PF y deja 2.29 trades/mes.
El filtro no selecciona: destruye.

Por año (filtrado), con muestras minúsculas:

| Year | n | WR % | PF | EV neto |
|---|---:|---:|---:|---:|
| 2024 | 23 | 26.09 | 0.731 | −11.35 |
| 2025 | 12 | 41.67 | 1.479 | +15.92 |
| 2026 | **4** | 50.00 | 2.070 | +30.50 |

n=4 en 2026. Cualquier lectura por año aquí es ruido.

## 4. No reproduce F7 — y F7 no es auditable

| | F7 (en memoria) | OR-CB-V2 (regenerado) |
|---|---:|---:|
| threshold | 0.4025 | 0.50 (fallback) |
| n OOS | 90 | 39 |
| EV neto | +13.9 | +1.33 |
| PF | 1.41 | 1.035 |

La diferencia es grande. Como el script, el modelo y la configuración de F7 se
perdieron, **no puedo determinar por qué**. Las posibilidades incluyen: un filtro
de meses que no repliqué, otras features, otro split, otros hiperparámetros — o
que F7 tuviera una fuga metodológica no detectada.

**Recomendación honesta: dejar de tratar "OR-CB pasó F7" como un hecho
establecido.** No es verificable y el intento limpio de regenerarlo no lo
confirma.

## 5. Consecuencia

Por el preregistro, FAIL → **no se desbloquea el forward de OR-CB**. El modelo
congelado (`orcb_v2_model.cbm` + `orcb_v2_config.json`, hasheados) queda
archivado como artefacto del intento, no como filtro utilizable.

## 6. Observación descriptiva (no es un resultado promovido)

El bracket **fijo 120/55 SIN filtro** da +3.945 ticks netos y PF 1.106 en FRESH
con 18.27 trades/mes — mejor que el trailing 50/20/40 en ambas direcciones
(−0.577). Aparece en la salida obligatoria como línea de comparación, no fue la
pregunta preregistrada, y su PF 1.106 queda por debajo de 1.15. **Si interesa,
requiere su propio preregistro**; no se promueve desde aquí.

`INFORMATION_STATUS=ORCB_V2_FAIL_FILTER_DEGRADES_BASELINE`
