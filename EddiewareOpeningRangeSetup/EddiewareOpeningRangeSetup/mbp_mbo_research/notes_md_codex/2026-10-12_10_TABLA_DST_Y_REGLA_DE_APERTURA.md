# Tabla de resultados del periodo DST disponible en 2026

Registro histórico previo a la aclaración de que el cuerpo también debe ir a favor. La reproducción actualizada y el objetivo de automatización se documentan en [la nota 11](2026-10-12_11_REPRODUCCION_DEL_CUERPO_Y_OBJETIVO.md); no se sobrescriben aquí los resultados anteriores.

El usuario confirmó que acepta velas que abren fuera del rango de las 09:30 y cierran fuera por el lado de la ruptura. La referencia `baseline_1r` ya lo permite: esta aclaración no cambia el replay ni requiere ejecutar de nuevo los motores. La condición de abrir dentro sigue siendo una variante experimental.

Cobertura: 150 sesiones disponibles del 9 de marzo al 9 de octubre de 2026. Todas las sesiones corresponden a DST de Nueva York, UTC−04:00. Esta tabla no representa la temporada DST completa ni incluye la entrada del 12 de octubre, cuyos datos todavía no están en la carpeta.

Todas las políticas mantienen RR 1:1, stop detrás del imbalance, máximo una operación por día y los costes y ejecución del estudio congelado. Cada variante espera su primera señal válida hasta las 09:40.

| Entrada | Trades totales | Ganadores / perdedores | WR | PF neto con 1 NQ fijo |
|---|---:|---:|---:|---:|
| Setup base del usuario, permite abrir fuera | 82 | 34 / 48 | 41.46% | 0.588 |
| Variante: abrir dentro y cerrar fuera del OR | 39 | 21 / 18 | 53.85% | 1.308 |
| Variante: delta agresor alineado | 81 | 34 / 47 | 41.98% | 0.589 |
| Variante: imbalance completo fuera del OR | 76 | 32 / 44 | 42.11% | 0.614 |

WR = operaciones con resultado neto positivo / operaciones resueltas. PF = suma de ganancias netas / valor absoluto de la suma de pérdidas netas, con un contrato constante. Comisión supuesta: USD4 ida y vuelta por NQ; slippage de entrada y stop: un tick por lado según el modelo. Ninguna operación está censurada ni queda sin resolver. Los trades entre políticas se solapan: no se suman los cuatro conteos.

La apertura dentro del OR tiene PF en R de 0.960, frente al PF monetario de 1.308: el riesgo variable explica la diferencia. Es una pista exploratoria, todavía sin edge validado; los intervalos de expectativa incluyen cero. La aclaración del usuario no convierte esa variante en su setup original.

Fuentes locales: `C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/core_entry_replay/trades.csv`, `daily.csv` y `C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/core_entry_audit/policy_summary.csv`. Se conservan los resultados congelados del estudio anterior.
