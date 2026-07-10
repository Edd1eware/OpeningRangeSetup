# PROGRESO 14 — pivote a medición pura por shape + MFE (2026-07-09)

## Decisión del usuario

Cancelar WR/PF en el desglose por shape. Por ahora SOLO capturar el LVN por grupo de perfil
contextual (D, P, b, doble valle, trend, unknown) y medir su **máxima extensión** (MFE).
La estrategia se diseña DESPUÉS, con el banco multi-temporada completo.

Cambios aplicados:
- Excel `Summary` → sección "Shape cohort" ahora reporta por shape: eventos, días únicos,
  eventos/mes, MFE mediana/promedio/p90/máx, MAE mediana, tiempo mediano a MFE. Sin WR/PF.
- Telegram final de cada corrida → mismo desglose de frecuencia + MFE por shape.
- Los brackets TP/SL siguen guardándose por evento en `LVN_Events` (no se pierde nada);
  solo se dejó de resumirlos por shape.

## Medición actual del banco (DST 2025 + DST 2026, 467 eventos, 13 meses)

| Shape ctx | n eventos | ev/mes | MFE med | MFE prom | MFE p90 | MFE máx |
|---|---:|---:|---:|---:|---:|---:|
| unknown | 186 | 14.3 | 105t | 131t | 280t | 485t |
| trend_up | 150 | 11.5 | 105t | 171t | 505t | 745t |
| trend_down | 110 | 8.5 | 82t | 128t | 304t | 465t |
| double | 20 | 1.5 | 162t | 181t | 372t | 520t |
| D | 1 | 0.1 | 155t | — | — | 155t |
| P / b puros | 0 | — | — | — | — | — |

Observaciones de MEDICIÓN (no de estrategia):

1. **P y b puros casi no existen** como ganador del clasificador en 08:30–09:30 de NQ; el
   contexto premarket se reparte entre trend_up/trend_down/unknown. Si se quiere estudiar
   P/b habrá que usar las probabilidades continuas (buckets de prob_P/prob_b), no la
   etiqueta dura.
2. **unknown es el grupo más frecuente** (14.3/mes) con MFE mediana 105t — igual de móvil
   que trend_up en mediana. Confirma la regla del usuario: shape imperfecto ≠ descartable.
3. **double es raro (1.5/mes) pero con la MFE mediana más alta (162t)** — el valle doble
   parece producir los recorridos más largos cuando aparece. n=20, solo medición.
4. trend_up tiene la cola más gorda (p90 505t, máx 745t): las extensiones monstruo viven ahí.
5. La MFE mediana global ronda 100t — coherente con que el bracket 80/80 fuera el único
   positivo en el análisis anterior: los eventos "quieren" moverse ~100 ticks.

## Cadena autónoma activa (si el usuario no está)

1. DST 2024 corriendo (task encadenado) → al terminar arranca solo DST 2022 desde mediados
   (2022-06-15 → 2022-11-04, feriados US/CME auto-excluidos).
2. Al terminar 2022: consolidar banco 4 tramos (2022m + 2024 + 2025 + 2026), regenerar
   medición por shape (frecuencia + MFE año×año), **analizar opciones CON EL LENTE LUCID
   $150k**: el objetivo es pasar la cuenta sin tocar el max DD diario ni la pérdida máxima
   total (MaxDD $4,500 = 900 ticks NQ a $5/tick; máx 3 contratos). Por grupo/candidato:
   distribución de MAE y pullbacks vs presupuesto de DD, peores secuencias de días,
   cuántos eventos malos seguidos soporta el buffer con 1/2/3 contratos, y cuáles
   grupos son ejecutables (o combinables) dentro de ese presupuesto. **Enviar resumen con
   opciones por Telegram.** Nota: confirmar con el usuario las reglas exactas de Lucid
   (DD diario, trailing vs EOD) antes de la simulación formal de Fase 3.
3. Excels intactos siempre; reintentos 3×60s por fecha; frontera de datos registrada en
   manifest si 2022 no tiene replay disponible.
