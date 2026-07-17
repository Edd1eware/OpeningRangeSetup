# Plan post-corrida — Trades que nacen mal

## Orden automático

1. No tocar la corrida activa ni sus procesos de Replay.
2. Esperar salida limpia del runner X10 y su supervisor.
3. Auditar completitud de todas las sesiones `2022-04-04` a `2026-07-16`.
4. Si existen huecos, ejecutar Historia X10 sin `--force`, sin `--reset-state` y
   con bloqueo de mouse/fail-fast; los terminales existentes se saltan.
5. No abrir el holdout mientras exista una sola sesión sin CSV terminal v23.
6. Ejecutar `born_bad_trade_research.py` sólo con la muestra completa.
7. Publicar reporte y visualizaciones en Telegram bajo
   `ANALISIS  FAMILIAS A, B, C, ETC. / GRUPO D`.
8. Copiar el hallazgo a `contexto_features_atas`.
9. Enviar `ya termine todos mis procesos` únicamente al concluir todo lo anterior.

Todos los Telegram de progreso, transición, error, reporte y cierre incluyen
`Timer etapa`. Los mensajes periódicos del Replay calculan la ETA con las
duraciones X10 observadas; una etapa terminada muestra `00:00` y una etapa fallida
muestra `DETENIDA`.

## Definiciones congeladas

- Grupo A: ganador.
- Grupo B: perdedor con `MFE > 30`.
- Grupo C: perdedor con `2 < MFE <= 30`.
- Grupo D: perdedor con `MFE <= 2`.

MFE, MAE, resultado y duración sólo etiquetan retrospectivamente; nunca son
predictores. La estrategia, Liquidity Burst, TP, SL y gestión permanecen intactos.

## Protocolo de velocidad diagnóstica

- X10 sigue siendo la única fuente oficial de outcomes, PnL y validación de la
  estrategia.
- Si X10 no permite medir objetivamente una feature microestructural, se autoriza
  una captura diagnóstica separada empezando por X2 y usando X1 sólo si X2 sigue
  siendo insuficiente.
- Las fechas diagnósticas se pre-registran y no se eligen por su resultado.
- X1/X2 sólo pueden aportar snapshots causales anteriores a la entrada; nunca
  sustituyen trades X10 ni se usan para mejorar PF/WR.
- Toda feature común debe conservar definición, timestamp y signo entre
  velocidades; cualquier discrepancia invalida esa feature hasta explicar la
  causa.

## Entregables automáticos

- Ranking Grupo D vs A.
- Ranking Grupo D vs todos los demás.
- Pruebas univariadas con corrección BH y tamaño de efecto.
- Mutual information, Random Forest, árboles, permutation importance y CatBoost
  cuando esté disponible.
- Validación cronológica discovery/validation/holdout.
- Catálogo matemático de nuevas features causales.
- Lista priorizada de variables faltantes para Build Alpha.
- Reporte Markdown, CSV, manifiesto y gráficas.
