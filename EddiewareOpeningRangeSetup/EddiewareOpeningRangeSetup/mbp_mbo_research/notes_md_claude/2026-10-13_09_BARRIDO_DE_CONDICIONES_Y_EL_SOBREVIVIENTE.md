# 09 — Barrido de diez condiciones diarias, y la única que sobrevive todo

Fecha: 2026-10-13. Scripts: `48_drift_condition_scan.py`, `49_condition_combination.py`.
Reportes: `drift_condition_scan.csv`, `condition_combination.csv`. **Costo: cero.**

## La lente

La geometría de la nota 08 colapsa toda la búsqueda a un número. Como `2P−1 ≈ μb/σ²`, una condición vale
exactamente su deriva de sesión diurna dividida entre el cuadrado de la volatilidad que arrastra. Rankear por μ
sola premiaría a las ruidosas; **rankear por μ/σ² es el orden honesto**.

Medido sobre historia diaria gratis, que es la muestra correcta para una pregunta de frecuencia diaria: ^GSPC
desde 1962 son 16,213 sesiones, ^NDX desde 1985, NQ=F desde 2000.

## Las diez condiciones, declaradas antes de correr

Todas exactamente derivables del calendario o de las barras de la sesión previa, así que ninguna depende de una
lista escrita a mano, y todas con respaldo publicado en vez de inventadas aquí: turn of month +1..+3; tras día
de −1σ y de −2σ (reversión de corto plazo); tras día de +1σ (el espejo); primera sesión tras feriado; lunes tras
semana negativa; semana de OpEx; ventana de Santa; tras cierre de capitulación (día abajo cerrando en el 10%
inferior de su rango); tras dos días negativos.

## Lo que pasa Bonferroni

Con 10 condiciones × 3 instrumentos el α honesto es **0.0017**, no 0.005. Sobreviven tres celdas, todas en
^GSPC, donde 64 años dan la potencia:

| condición | n | deriva | σ | μ/σ² | p | WR | placebo p |
|---|---:|---:|---:|---:|---:|---:|---:|
| C8 ventana Santa | 450 | +0.1527% | 0.89% | 0.1918 | 0.0030 | 0.5778 | 0.4892 |
| **C4 tras día +1σ** | 2,250 | +0.1098% | 0.95% | 0.1229 | **0.0000** | 0.5711 | 0.4799 |
| **C1 turn of month** | 2,334 | +0.1005% | 0.96% | 0.1084 | **0.0001** | 0.5613 | 0.5975 |

(C8 con p=0.0030 queda arriba de 0.0017, así que estrictamente tampoco pasa.)

**Aviso de lectura que importa mucho:** ^GSPC gana el ranking de μ/σ² sólo porque su σ es 0.89-0.96% contra
1.7-2.2% de NQ. El ratio favorece al instrumento de baja volatilidad, pero el que se opera es NQ. Las historias
largas sirven para **establecer si el efecto existe**, no para decidir qué operar.

## Dos cosas que contradicen lo que yo asumía

**C4 es momentum, no reversión.** Tras un día de +1σ el índice sigue subiendo (n=2,250, p=0.0000) y tras uno de
−1σ **baja** (−0.0386%, t=−2.57, p=0.0102). La literatura de reversión de corto plazo no describe la sesión
diurna del índice. Pero C4 no replica: ^NDX da +0.0631% (p=0.60) y NQ=F da **−0.0346%**. No sirve para NQ.

**C6, lunes tras semana negativa, es un setup CORTO**, y fuerte: ^GSPC −0.1360% (t=−4.97, p=0.0000), ^NDX
−0.0970% (p=0.0153). Tampoco replica en NQ=F (+0.0590%, p=0.81).

## Lo mejor para NQ en concreto

| condición en NQ=F | n | deriva | μ/σ² | p |
|---|---:|---:|---:|---:|
| C9 tras cierre de capitulación | 344 | **+0.2069%** | 0.0420 | 0.149 |
| C10 tras dos días negativos | 1,328 | +0.1389% | 0.0390 | 0.028 |
| C1 turn of month | 942 | +0.1088% | 0.0371 | 0.183 |

Ninguna pasa sola con el α corregido. La deriva más grande (C9, el doble que turn of month) tiene n=344.

## La combinación no se sostiene

Hipótesis motivada, con dirección declarada: el turn of month es una historia de **flujos** que llegan en
calendario, y "tras dos días negativos" es una historia de **precio**. Flujos que entran a un mercado que acaba
de caer deberían empujar más fuerte. Es la misma predicción que el test de retorno del mes previo rechazó en la
nota 06, pero sobre debilidad de corto plazo, que es otra pregunta y no un segundo intento de la misma.

| instrumento | C1 sola | C10 sola | C1 ∩ C10 | n | p |
|---|---:|---:|---:|---:|---:|
| ^GSPC | +0.1005% | +0.0078% | **+0.0825%** | 483 | 0.2571 |
| ^NDX | +0.1461% | +0.0797% | +0.3245% | 266 | 0.0196 |
| NQ=F | +0.1088% | +0.1389% | +0.2310% | 188 | 0.2161 |

En ^NDX y NQ=F la combinación duplica la deriva. **En ^GSPC la diluye**, y ^GSPC es la muestra con más potencia
de las tres. Y `C1 pero NO C10` da +0.1053% con p=0.0002 en ^GSPC, que es mejor que la combinación. Cuando el
instrumento mejor medido dice que no, no es un hallazgo. Además σ sube de 1.71% a 2.15% en NQ=F, así que μ/σ²
sólo pasa de 0.0371 a 0.0502: la mitad de la ganancia aparente se come en volatilidad.

**Veredicto: la combinación no está soportada.** Queda escrita para que nadie la vuelva a probar creyendo que es
nueva.

## El sobreviviente

Turn of month, días +1..+3, sesión diurna. Positivo en **cada década de cada instrumento**:

| década | ^GSPC t | ^NDX t | NQ=F t |
|---|---:|---:|---:|
| 1960 | +2.43 | — | — |
| 1970 | +2.08 | — | — |
| 1980 | +2.54 | +2.99 | — |
| 1990 | +3.32 | +3.08 | — |
| 2000 | +0.54 | +0.54 | +0.90 |
| 2010 | +1.36 | +1.34 | +1.45 |
| 2020 | +2.54 | +2.11 | +1.47 |

Siete décadas, tres instrumentos, **ningún signo negativo**, placebos limpios en los tres, p agrupada de 0.0001
en la muestra de 64 años, y el efecto vive entero en la sesión diurna (nota 06). Los 2000 y 2010 son flojos en
los tres a la vez, lo cual es coherente con un efecto arbitrado y luego revivido, no con ruido.

## Qué vale, en los términos del objetivo

Con la deriva de +0.1088% y σ=1.1145% medidas, la mejor configuración que respeta la regla de cerrar en el día
es **8 MNQ con stop de 94 puntos** y riesgo de $1,500: WR modelada 0.5164 contra breakeven 0.5040.

Metido en la política escasa de la nota 07: **P(pasar) ≈ 46.4% contra 43.3% sin ningún edge. Tres puntos.**

Eso es lo que vale, honestamente, el mejor hallazgo de esta línea. No es un edge que cambie la vida; es un
sesgo real, antiguo, replicado y chico, que empuja una probabilidad de pase de 43% a 46% cuando se combina con
una política de tamaño correcta. El resto del valor de hoy está en la política, no en el edge.
