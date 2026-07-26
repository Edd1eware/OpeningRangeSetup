# Preregistro OR-CB-V2 — regenerar y congelar el filtro CatBoost del ORB

Fecha: 2026-07-25
Autor: Claude Fable
Estado: **CONGELADO ANTES DE ENTRENAR**

## 0. Esto NO es una reproducción de F7

F7 quedó registrado en memoria (thr 0.4025, TP/SL 120/55, OOS n=90, EV +13.9t,
PF 1.41), pero **su script, su modelo y su configuración exacta se perdieron**.
Verificado: no existe `.cbm`/`.pkl`/`.joblib` del estudio, y
`orb_catboost_filter.py` es un walk-forward que no persiste modelo.

Por tanto **OR-CB-V2 es un estudio nuevo** que reconstruye el pipeline sobre el
mismo blueprint disponible. **Su resultado vale por sí mismo y puede diferir de
F7.** Si sale peor, ese es el dato — no se ajusta nada para parecerse a F7.

También se declara: F7 incluía un "filtro ene+dic validado era-blind" cuya
definición exacta no es recuperable. **No se incluye.** Añadir un filtro que no
puedo verificar sería peor que un test limpio sin él.

## 1. Datos y features

```text
sesiones  = raw_dbn_2\<fecha>\ohlcv-1s-full   (1,029 dias, 2022-04-25 .. 2026-07-01)
features  = las 73 causales PRE-breakout ya existentes en
            orb_features_labels_1s.csv  (ventanas 5/10/30/60/120 s:
            vol, rng, net, dir, vpt, liq, amh, vts, vvs, rvol, m1v, m1r
            + or_range_ticks, breakout_delay_s, dist_vwap, round_25/50/100,
            dist_pdh/pdl/pdc, direction_up)
```

Todas las features se calculan **antes** del instante de entrada (ventana causal
que termina en el breakout). No se añade ninguna feature nueva.

## 2. Etiqueta a regenerar

```text
entrada = primer breakout del OR 09:30 (UP o DOWN), al nivel del OR
bracket = TP 120 ticks / SL 55 ticks     (el de F7)
y = 1 si el TP se toca antes que el SL, 0 si el SL se toca primero
regla barra a barra conservadora sobre 1s; si en la misma barra el low toca SL,
gana el SL (pesimista). Timeout (ninguno tocado) -> caso excluido.
comision = 2.0 ticks
```

Breakeven WR con este bracket: `55/(120+55) = 31.43%`.

## 3. Split y congelación

```text
DEV   = 2022 + 2023      -> entrenamiento + validacion interna
        validacion interna = ultimo 20% de DEV por fecha (no aleatorio)
FRESH = 2024 + 2025 + 2026  -> DISPARO UNICO, jamas visto antes de congelar
```

### Hiperparámetros CatBoost — FIJADOS AHORA, sin tuning

```text
iterations = 300 | depth = 4 | learning_rate = 0.05
loss_function = Logloss | random_seed = 20260725 | verbose = 0
```

Deliberadamente modestos para limitar sobreajuste. **No se prueban otros.**

### Regla del threshold — declarada, no barrida

```text
thr = el MENOR p tal que la precision sobre la validacion interna >= 0.40
      (0.40 esta muy por encima del breakeven 0.3143; con TP/SL 120/55
       implica EV ~ +13 ticks netos)
si ningun p alcanza 0.40 -> thr = 0.50 y se reporta como tal
```

Se declara la **regla**, no un valor. El 0.4025 de F7 no se copia.

### Artefactos congelados (persistidos antes de tocar FRESH)

`orcb_v2_model.cbm`, `orcb_v2_config.json` (threshold, lista ordenada de
features, hiperparámetros, hashes), y `FROZEN_HASHES.sha256`.

## 4. Gate (sobre FRESH, los cuatro)

| # | Criterio | Umbral |
|---|---|---|
| C1 | EV neto por trade | > 0 |
| C2 | Profit Factor | > 1.15 |
| C3 | Años con EV neto > 0 | ≥ 2 de 3 |
| C4 | Frecuencia | ≥ 3 trades/mes |

C4 es laxo a propósito: un filtro selectivo con TP 120 opera poco por diseño.

PASS → modelo congelado utilizable, se desbloquea el forward de OR-CB.
FAIL → no se desbloquea; se documenta y OR-CB queda archivado.

## 5. Prohibiciones

No se re-entrena tras ver FRESH. No se ajustan hiperparámetros ni el bracket. No
se prueba otro threshold. No se añade el filtro de meses. No se excluye ningún
año. No se repite con otra semilla para mejorar el resultado.

`INFORMATION_STATUS=ORCB_V2_PREREGISTERED_NO_RESULT`
