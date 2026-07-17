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

## Definiciones congeladas

- Grupo A: ganador.
- Grupo B: perdedor con `MFE > 30`.
- Grupo C: perdedor con `2 < MFE <= 30`.
- Grupo D: perdedor con `MFE <= 2`.

MFE, MAE, resultado y duración sólo etiquetan retrospectivamente; nunca son
predictores. La estrategia, Liquidity Burst, TP, SL y gestión permanecen intactos.

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
