# Preregistro FORWARD-V1 — Gates de evaluación del forward

Fecha: 2026-07-25
Autor: Claude Fable
Estado: **CONGELADO ANTES DE QUE EXISTA UN SOLO TRADE FORWARD**

Este documento fija cómo se juzgará el forward **antes** de ver ningún resultado.
Es la única forma de que el forward signifique algo: si los umbrales se ponen
después, se ajustan a lo que salió.

## 1. ATRAPADOS v1 — forward en ATAS

### Configuración congelada (la que quedó desplegada)

```text
estrategia = TrappedFadeStrategy  (10_TrappedFadeStrategy.cs)
SL inicial          = 50 ticks
trailing activacion = +20 ticks
trailing distancia  = 40 ticks
cierre forzado      = 15:59 NY     ultima entrada = 15:50 NY
contratos           = 1  (escalera INACTIVA, ver seccion 3)
log                 = Nautilus_OR\features\atrapados_atas_replay.csv
```

### Gate (evaluación a los 2 meses de operación forward)

| # | Criterio | Umbral |
|---|---|---|
| A1 | EV neto por trade | > 0 |
| A2 | Profit Factor | > 1.15 |
| A3 | n mínimo de trades | ≥ 30 |
| A4 | Meses con EV neto > 0 | ≥ 1 de 2 |

Comisión asumida: 2.0 ticks por trade (misma constante del proyecto).

PASS en A1-A4 → se autoriza escalar tamaño y considerar fondeo.
FAIL → el edge no se confirmó fuera de muestra; se archiva.

**No se evalúa antes de los 2 meses ni de los 30 trades.** Mirar temprano y
decidir sería exactamente el sesgo que este preregistro previene.

## 2. OR-CB — BLOQUEADO, no se inicia

El forward de OR-CB **no puede arrancar** porque **el modelo congelado no existe
en disco**. Verificado:

```text
buscado: *.cbm, *.pkl, *.joblib, *model*.json  en Desktop y Documents
encontrado: solo frozen_core_baseline.joblib, de OTRO estudio
            (lb_absorption_breakout_frozen_20260720_r1)
orb_catboost_filter.py = evaluacion walk-forward, NO persiste modelo
threshold 0.4025 = no aparece en ningun artefacto localizable
```

El resultado F7 (thr 0.4025, TP/SL 120/55, OOS n=90, EV +13.9t, PF 1.41) está
registrado en memoria, pero **el modelo que lo produjo se perdió**. Reentrenar
generaría un modelo distinto, al que la validación OOS de F7 **no le aplica**.

**Consecuencia honesta:** para forward-testear OR-CB hay que primero regenerar y
congelar F7 (reentrenar + volver a validar OOS + persistir el `.cbm` y el
threshold). Eso es un trabajo aparte, y su resultado puede diferir del
registrado. No se finge un forward sobre un modelo que no existe.

## 3. Limitación declarada de ATRAPADOS: escalera de sizing inactiva

La estrategia implementa la escalera 5/3/1 (5 contratos si ADN∩VA, 3 si VA, 1 en
otro caso), pero necesita un archivo diario:

```text
Nautilus_OR\features\atrapados_sizing_YYYY-MM-DD.txt
formato: vaLow,vaHigh,adn      (adn = 1 o 0)
```

Ese archivo **no tiene generador** y **la definición de ADN se perdió** (vivía en
`Desktop\Codex_cotexto\ATRAPADOS_master_hallazgos_02_07_2026.md`, carpeta que ya
no existe). Sin el archivo, `LadderContracts()` devuelve siempre `ContractsBase`
= 1 contrato.

**Esto no invalida el forward.** El gate A1-A4 mide EV y PF **en ticks**, que son
independientes del tamaño. La escalera afecta el $ ganado, no si el edge existe.
Se puede añadir después sin invalidar lo medido.

## 4. Prohibiciones

No se cambian SL/trailing/horarios durante el forward. No se evalúa antes del
plazo. No se relajan umbrales al ver resultados parciales. No se reinicia el
contador tras una racha mala. Cualquier cambio a la estrategia reinicia el
forward desde cero y se documenta.

`INFORMATION_STATUS=FORWARD_V1_PREREGISTERED_NO_TRADES_YET`
