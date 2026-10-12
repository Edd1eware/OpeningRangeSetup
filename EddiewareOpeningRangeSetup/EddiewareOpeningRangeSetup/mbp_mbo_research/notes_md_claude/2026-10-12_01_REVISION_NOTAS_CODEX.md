# Revisión independiente de las notas de Codex (01–13)

Fecha: 2026-10-12. Autor: Claude. Fuente revisada: `../notes_md_codex/` (14 archivos, README + notas 01–13).

Esta nota **no** ejecuta código nuevo ni recalcula métricas. Es una lectura crítica de lo que Codex reportó, con el objetivo de separar lo demostrado de lo que todavía es ruido.

## 1. Resumen de lo que Codex entregó

| # | Nota | Hallazgo clave |
|---|---|---|
| 01 | Objetivo y reglas | Setup congelado: OR 09:30–09:31 NY, M1, cierres 09:32→09:40, cuerpo + imbalance diagonal + VWAP a favor, ratio 300%, mínimo 70, filas de 5 ticks, SL 5 ticks tras el imbalance alineado más lejano, RR 1:1, máximo 1 operación/día. Datos: 150 sesiones, 2026-03-09 → 2026-10-09 |
| 02 | Caso visual 12-Oct | Short, SL 30977.50 / TP 30947.50 / entry ≈30962.50 = 60 ticks por lado. No reconstruible: la carpeta local termina el 09-Oct |
| 03 | Auditoría heredada | `full_spec_far.csv` tiene 26 operaciones reales repetidas para 5 RR. Contar 130 filas sería incorrecto. Guardas de bordes diagonales invertidas en el código previo |
| 04 | Control del footprint | 145 primeras rupturas, bracket fijo 60/60: el grupo con imbalance a favor rinde **peor** que tomar todas (−12.72 ticks, IC95% [−33.96, +8.52]) |
| 05 | Replay RR 1:1 | 82 operaciones, WR 41.46%, PF 0.588, −15.90 ticks/trade, −0.3163R |
| 06 | RR fijos | RR 0.75 / 1 / 1.5 / 2 sobre las mismas entradas: **las cuatro negativas**, en ambas mitades cronológicas |
| 07 | Trailing + feature | Trailing desde +1R mejora a −9.58 ticks (sigue negativo) y la mejora se concentra en junio. El feature `trend_efficiency_entry` **empeoró** la segunda mitad |
| 08–09 | Edge de entrada | 4 políticas comparadas. Única pista positiva en dinero: apertura dentro del OR |
| 10–11 | Cuerpo a favor | Corrección de fidelidad: cuerpo estrictamente direccional. 82 → 81 operaciones, sin cambio material |
| 12 | Paridad ATAS/Databento | 647/650 footprints idénticos por hora de evento; rejilla identificada = tick superior de un intervalo de 5 ticks (ceil, no "más cercano") |
| 13 | Setup calibrado | Referencia 78 trades / control dentro 35 trades. Ver tabla siguiente |

## 2. Estado actual del edge

| Política RR 1:1 | Trades | WR | PF 1 NQ | PF en R | Neto 1 NQ | Neto R |
|---|---:|---:|---:|---:|---:|---:|
| Reglas del usuario (apertura fuera permitida) | 78 | 42.31% | 0.602 | 0.572 | −USD 5,937 | −23.56R |
| Control: apertura dentro del OR | 35 | 54.29% | 1.382 | **0.959** | +USD 1,515 | **−0.79R** |

Breakeven con RR 1:1 y coste de ~1.8 ticks sobre un riesgo mediano de ~47 ticks está en WR ≈52–53%. El control queda justo en el filo, no por encima.

## 3. Objeciones

### 3.1 La divergencia PF monetario vs PF en R es la bandera roja principal

PF 1.382 en dólares contra 0.959 en R significa que el resultado positivo proviene de operaciones con SL grande, no de capacidad direccional. Con riesgo constante —que es como se opera una evaluación Lucid con DLL y MLL— la política **pierde**.

Codex lo señala correctamente en las notas 09, 10 y 13. El punto a subrayar: para el objetivo declarado (pasar LucidPro 50K/100K) el PF monetario con un contrato fijo y SL entre 1 y 254 ticks **no es la métrica relevante**. La decisión debería tomarse sobre R, y en R no hay nada.

### 3.2 Tamaño de muestra insuficiente para la hipótesis declarada

El usuario estima WR ≥60%. Para distinguir 60% de un breakeven de 52% con potencia del 80% y alfa 0.05 hacen falta del orden de 250–300 operaciones. Hay 35. El intervalo Wilson reportado (38.19%–69.53%) contiene tanto el breakeven como el 60%: la muestra no puede decidir entre las dos hipótesis.

A 5 operaciones/mes, llegar a 250 trades requiere ~4 años de sesiones.

### 3.3 Multiple testing acumulado

Políticas y variantes evaluadas sobre las mismas 150 sesiones a lo largo de las notas 04–13: control de footprint, RR 0.75/1/1.5/2, trailing 30min, trailing 15:55, feature condicional, open dentro del OR, delta agresor alineado, imbalance completo fuera, cuerpo estricto, setup calibrado, control calibrado dentro. Son del orden de 12–15 comparaciones.

"Apertura dentro del OR" es la superviviente de ese barrido. Codex ajusta por 4 políticas dentro de un estudio concreto, pero reconoce explícitamente que el ajuste **no cubre las búsquedas previas**. Con ~15 pruebas acumuladas, un p-valor nominal de 0.05 corresponde a un Bonferroni de ~0.0033, y ningún resultado se acerca.

Este patrón es el mismo documentado en el proyecto para la regla de crossline de cuerpo SPY/USTEC: el ganador de un barrido amplio no sobrevive fuera de muestra.

### 3.4 Los PF mensuales altos son ruido

| Mes | Trades dentro | PF 1 NQ dentro |
|---|---:|---:|
| Abril | 7 | 3.039 |
| Junio | 4 | 7.038 |
| Agosto | 6 | 6.217 |

Un PF de 7.038 sobre 4 operaciones no es información. Es el mismo fenómeno de la nota 07, donde toda la mejora del trailing venía de junio (+763 ticks de diferencia sobre una mejora total de +518; fuera de junio, el trailing **empeora** −245 ticks).

### 3.5 Contradicción interna no resuelta: el imbalance

La nota 04 mide, con bracket fijo y sin VWAP, que exigir imbalance a favor **empeora** el resultado en −12.72 ticks frente a tomar todas las rupturas. La nota 13 mantiene el imbalance como condición obligatoria y además lo usa para colocar el SL.

Nadie ha medido el setup calibrado **sin** la condición de imbalance. Si el footprint no aporta dirección, el SL estructural derivado de él tampoco tiene fundamento, y el riesgo mediano de 47 ticks con rango 1–254 pasa a ser arbitrario.

### 3.6 Riesgo de 1 tick: no ejecutable

Dos operaciones (30-Jun y 08-Jul) tienen primer print exactamente sobre el SL y riesgo simulado de 1 tick. Codex las conserva marcadas, lo cual es correcto metodológicamente. En términos operativos, un SL de 1 tick en NQ no existe: ni el spread ni la cola lo permiten. Cualquier métrica en R está distorsionada por esas filas, en ambos sentidos.

## 4. Lo que está bien hecho

| Punto | Detalle |
|---|---|
| Corrección de bordes | Guardas diagonales invertidas detectadas en `05_l2_features.py:153` y `12_full_spec.py:160-168`, con verificación de que el cambio no altera las 145 rupturas |
| Causalidad | Truncar el futuro o inyectar precios extremos exactamente al cierre no cambia los features. 19 + 10 + 9 + 13 + 6 tests según el motor |
| Paridad de datos | 647/650 footprints idénticos celda por celda contra exports ATAS; rejilla ceil-5 identificada desde prints sin agrupar |
| Honestidad estadística | Intervalos siempre reportados, resultados negativos publicados, fechas desfavorables conservadas, ningún periodo ya inspeccionado presentado como out-of-sample |
| Separación ticks vs R | Se insiste en que las dos métricas pueden tener signos distintos y no se elige la favorable |
| No se compraron datos | Criterio de gasto respetado: sin candidato prometedor, no hay descarga |

## 5. Pruebas pendientes, ordenadas por coste

| # | Prueba | Coste | Qué decidiría |
|---|---|---|---|
| 1 | **Placebo**: "apertura dentro del OR" **sin** imbalance y **sin** VWAP, mismo SL y RR | USD 0 | Si el EV no cae, el order flow no aporta nada y la pista es solo "ruptura desde dentro del rango" |
| 2 | **Ablación por componente**: quitar imbalance / quitar VWAP / quitar cuerpo, uno a la vez | USD 0 | Cuál de las tres condiciones sostiene el resultado. La nota 04 sugiere que el imbalance resta |
| 3 | **Fijar la métrica de decisión en R** y recalcular el histórico con sizing por riesgo constante y contratos enteros | USD 0 | Elimina la ilusión del PF monetario y acerca el modelo a la mecánica de Lucid |
| 4 | **Cap de riesgo** (p. ej. descartar SL fuera de 20–80 ticks) | USD 0 | Mejora probable, pero es un parámetro adicional: exige registrarlo antes y contarlo en el ajuste por multiple testing |
| 5 | Comprar más datos de Databento | ~USD 80 disponibles | Solo después de que 1–3 den señal. Sin eso, es gasto sobre una hipótesis ya debilitada |

## 6. Conclusión

No hay edge demostrado con las reglas codificadas. La referencia del usuario pierde de forma consistente (PF 0.602, −23.56R en 78 operaciones). La única pista viva —apertura dentro del OR— sobrevive en dinero pero muere al normalizar por riesgo (PF_R 0.959), que es justamente la métrica que determina si una cuenta Lucid se pasa o no.

Esto no prueba que el setup del usuario no funcione en su ejecución discrecional real. Prueba que **el modelo actual no reproduce ese resultado**. La diferencia entre el 42% modelado y el 60% estimado por experiencia requiere localizar dónde divergen selección, rejilla, stop o ejecución, no ajustar parámetros hasta alcanzar la cifra.

Antes de gastar en datos nuevos, las pruebas 1–3 cuestan cero y pueden cerrar la pregunta.
