# 055 — V9 conflicto + reclaim fade falla

Fecha: 2026-07-26

Oposición cross-market >=2 y reclaim NQ <=15 s produjo solo 11 trades en 414
sesiones, EV `-0.401R`, PF `0.475`, frecuencia 0.52/mes y cero periodos
positivos. No es viable para Lucid 150K.

La serie V1–V9 apunta a un problema común: el OR de un minuto produce entradas
sin estabilidad aun con breadth, gap, reclaim o LB. V10 cambiará a OR5,
aceptación por cierre, confirmación ES y pullback defendido.

`INFORMATION_STATUS=LUCID150K_SNIPER_V9_FAIL`
