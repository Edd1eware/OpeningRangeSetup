# Dictamen Claude/Fable — ronda 001

Sesión: `dd40ebd9-c0db-44a0-805b-0ba5a3a34011`

## Objetivo invariable

Separar absorción limpia de breakout limpio antes del movimiento, sin lookahead
ni sobreajuste.

## 1. Acuerdos con Codex

| # | Acuerdo |
|---|---|
| 1 | Test Cero MFE/MAE es circular. A exige `MFE>=TP, MAE<=20`; B exige `MAE>=SL, MFE<=20`. Las etiquetas son funciones umbralizadas de MFE/MAE; contrastarlas en MFE/MAE es tautología. Prohibirlo es correcto |
| 2 | Las 100 sesiones fueron seleccionadas por familia; no son censo. Sin valor para prevalencia, calibración final ni confirmación prospectiva |
| 3 | Pseudo-eventos deben compartir régimen de apertura (08:30–09:30 CT), no toda la jornada |
| 4 | Prohibido definir etiquetas con las mismas features MBO que luego intenten separarlas |
| 5 | El gate sólo puede ser discovery/paro, nunca confirmación prospectiva: A/B ya conocidos, muestra estratificada, endpoint diseñado tras ver fallos |
| 6 | Fuente uniforme Databento para 100/100 es mejor que mezclar 86 ATAS y 14 Databento |

## 2. Desacuerdos

| # | Desacuerdo | Fundamento |
|---|---|---|
| 1 | Nulo equivocado. La permutación de etiquetas favorece el rechazo | El primer segundo posterior a `t_decision` está dentro de la trayectoria que genera Result_Label/MFE/MAE. Bajo random walk con barreras TP/SL, el desplazamiento temprano condicionado al resultado terminal ya difiere sin estructura explotable. El filtro limpio amplifica el efecto |
| 2 | Un tick absoluto no mide utilidad | Sin baseline mecánico, un tick puede proceder de la geometría de barreras |
| 3 | MDE=2 y potencia 0.80 pueden ser inalcanzables con n=70 | Con desviación de 3–5 ticks, el MDE al 80% sería aproximadamente 2–3.4 ticks |
| 4 | Sin divergencia a 1 segundo no implica que MBO predecisión carezca de señal | Divergencia reactiva no es condición necesaria ni suficiente de predictibilidad |
| 5 | Mantener etiquetas terminales de outcome es la raíz del problema | El objetivo de fondo exige etiqueta microestructural independiente |

## 3. Riesgos señalados

1. Lookahead estructural al condicionar en A/B y medir una parte de la misma
   trayectoria futura.
2. Selección amplificadora al estratificar por familias limpias.
3. Tercera iteración post hoc sobre los mismos 70 eventos.
4. Un PASS barato podría autorizar más minería MBO sin evidencia.

## 4. Decisión de Claude

**MODIFICAR_DISEÑO_ANTES_DE_DESCARGAR**

No reanudar la descarga actual. Tampoco detener todavía toda la línea.

## 5. Diseño único propuesto por Claude — Gate Cero v2

1. Descargar `trades` Databento de 08:30–10:30 America/Chicago para las 100
   sesiones, con contrato verificado.
2. Conservar el endpoint p0/p1 a un segundo.
3. Reemplazar permutación por un nulo mecánico de barreras:
   - pseudo-decisiones 08:30–09:30 CT estratificadas por minuto;
   - excluir ±60 segundos de bursts;
   - lado 50/50;
   - heredar bracket real de la sesión;
   - resolver TP/SL/MFE/MAE durante 60 minutos;
   - no resuelto pasa a pseudo-C;
   - 1,000 réplicas.
4. PASS exige:
   - delta real superior al percentil 95 del delta mecánico;
   - delta real menos mediana del nulo >=1 tick;
   - signo B>A en cada año.
5. Controles:
   - último trade ATAS frente a p0, discrepancia máxima 2 ticks;
   - contrato correcto;
   - trades antes y después;
   - sin redondeo.
6. PASS sólo permitiría discovery de una entrada confirmada a un segundo, no
   otra ronda de clasificadores MBO snapshot.
7. Veredictos: PASS, FAIL mecánico o INTEGRIDAD FAIL.

## 6. Condiciones de paro de Claude

- Detener la taxonomía terminal si el delta real cae dentro del nulo o el signo
  anual es inconsistente.
- Detener ante integridad no reparable.
- Abrir segunda ronda si Codex rechaza el nulo mecánico.
- Respetar una sola revisión.
- Detener si falla sensibilidad del detector o reconciliación externa.

## 7. Cierre de Claude

Claude concluye que el objetivo de fondo sólo se responde con una etiqueta
mecánica de libro independiente, no con etiquetas de outcome. Su Gate Cero v2
decidiría si la taxonomía terminal merece un estudio de entrada confirmada a un
segundo; no la convertiría en verdad microestructural.

