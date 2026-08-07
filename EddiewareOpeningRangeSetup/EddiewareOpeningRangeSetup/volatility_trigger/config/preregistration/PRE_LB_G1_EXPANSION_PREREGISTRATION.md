# Prerregistro G1: ¿el libro pre-LB predice expansión, no dirección?

Fecha: 2026-07-28
Audit ID: `PRE_LB_G1_EXPANSION_V1`
Estado: `BEFORE_ANY_G1_OUTCOME`
Hipótesis número 2 sobre la matriz F3, de un presupuesto de 5

## 1. Motivación

La línea direccional está cerrada:

```text
PRE_LB_PRECURSOR_F5 = NO_DISCOVERY_SIGNAL_CLOSE_LINE
delta -0.0360, permutación p 0.730, 0/4 folds
```

El libro Top-10 y el perfil causal pre-LB no dicen **hacia dónde** se mueve el
precio tras el Liquidity Burst. Empeoran la predicción.

La evidencia acumulada de esta investigación apunta a que el LB localiza
**volatilidad**, no dirección. G1 pregunta exactamente eso, y es la primera
hipótesis que se alinea con lo que la evidencia sí sugiere en vez de insistir
en lo que ya falló.

Esta no es una reinterpretación del FAIL de F5 ni un rescate. Es un estimand
distinto, con un target distinto, declarado antes de mirar ningún resultado de
expansión.

## 2. Pregunta y estimand

> Condicionado a que el libro sea mecánicamente utilizable, ¿el Top-10 local y
> el perfil causal pre-LB predicen si el precio **expandirá** 16 ticks en
> cualquier dirección dentro de 5 s, mejor que un baseline causal de atributos
> del LB, precio y tape?

El resultado máximo posible sigue siendo `DISCOVERY_ONLY_SIGNAL`. No rescata
V3, no rescata F5, no abre validation ni holdout.

## 3. Target

Derivado mecánicamente de los labels V3 ya congelados, sin recomputar nada:

```text
EXPANSION     = CONTINUATION  OR  REVERSAL
NO_EXPANSION  = NO_EXPANSION
AMBIGUOUS     = abstención, excluida, igual que en F5
```

El colapso es una función determinista de la clase resuelta. No hay umbral
nuevo, ni horizonte nuevo, ni política de abstención nueva. Se conservan
`16 ticks / 5 s / MID actual / depth age <= 250 ms / spread 1-4`.

Queda prohibido:

- cambiar el umbral de 16 ticks;
- cambiar el horizonte de 5 s;
- reintroducir la dirección como target, feature o filtro;
- definir un target continuo de magnitud si el binario falla.

## 4. Información ya conocida, declarada por transparencia

Al ejecutar F5 quedaron a la vista los conteos marginales de clase sobre las
2559 filas resueltas:

```text
CONTINUATION   587
REVERSAL       525
NO_EXPANSION  1447
```

Por tanto la tasa base de `EXPANSION` es conocida: `1112 / 2559 = 43.45%`.

Esto es una marginal, no una asociación: no dice nada sobre si las features
predicen la clase. Se declara igualmente para que conste que G1 se diseña
sabiendo la prevalencia. Nada en el protocolo depende de ese número: la métrica
es balanceada por clase, así que la prevalencia no puede inflar el resultado.

Ninguna asociación feature-target ha sido observada para el target binario.

## 5. Features

Exactamente las mismas 60 de la matriz F3 congelada, sin añadir, quitar ni
transformar:

```text
feature_matrix.parquet
SHA256 9AAA5F6C22D17B435D39203BE49699933C784607DBCAAD947C93F47E57906336
freeze de salida 42B29BFD30D477E69222FEC3D194D8663DAC5C0CA13FD01580B2D9967E62B516
```

Composición de modelos idéntica a F5, incluida la enmienda de sustitución
`GEMINI_F5_MODEL_SET_AMENDMENT: APPROVE_A`:

```text
M0_BASE   = BLB + CTL + PX + TAPE                       32
M_DOM_W1  = M0_BASE + DOM state + DOM W1                44
M_PRF     = M0_BASE + F11                               40
M_ALL_W1  = M0_BASE + DOM state + DOM W1 + F11          52
M_ALL_W5  = M0_BASE + DOM state + DOM W5 + F11          52
M_ALL_W30 = M0_BASE + DOM state + DOM W30 + F11         52
B_PRICE   = PX                                           9
B_PRICE_PLUS_PRF = PX + F11                             17
```

Se prohíbe cualquier selección, pruning o reordenamiento de features motivado
por los resultados de F5.

## 6. Métrica

```text
BBLL = media sobre las 2 clases de(
           media( -log(probabilidad de la clase verdadera) dentro de la clase )
       )

Delta = BBLL(M0_BASE) - BBLL(M_ALL_W1)
```

Positivo significa mejora. Es la versión binaria exacta de la BMLL usada en F5:
cada clase pesa igual, así que la prevalencia de 43.45% no puede regalar un
delta positivo.

El modelo pasa de multinomial a binomial. Todo lo demás del pipeline queda
idéntico y congelado:

```text
StandardScaler ajustado sólo en train
LogisticRegression, L2, C=1.0, lbfgs, max_iter=10000
class weight = n_train / (2 * n_train_class), sólo train
sin tuning, sin selección, sin calibración
```

## 7. Folds, idénticos a F5

Sobre las mismas 104 sesiones elegibles en orden cronológico, numeradas desde
la matriz congelada y nunca desde las filas que sobreviven al join:

```text
fold 1  train 1-40   test 41-56
fold 2  train 1-56   test 57-72
fold 3  train 1-72   test 73-88
fold 4  train 1-88   test 89-104
```

## 8. Primary único

```text
M_ALL_W1 vs M0_BASE
muestra matched COMBINED_W1_SUPPORT, features finitas de ambos modelos
```

Seis gates, todos obligatorios, con las mismas semillas congeladas:

```text
1. Delta >= 0.01
2. bootstrap por sesión, 2000 reps, seed 20260727, límite inferior CI95 > 0
3. permutación circular intrasesión no-cero, 1000 refits completos,
   seed 20260727, p <= 0.05
4. Delta > 0 en >= 3 de 4 folds
5. Delta BUY > 0
6. Delta SELL > 0
```

Los gates 5 y 6 se conservan aunque el target sea no direccional. Su función
aquí es de **simetría**: si el libro predice expansión, debe hacerlo para
bursts de compra y de venta. Un efecto que sólo aparece en un lado de un target
no direccional es señal de artefacto, no de edge.

## 9. Secundarios

Los mismos cinco de F5, con el target binario, Benjamini-Hochberg `q <= 0.10`:

```text
M_DOM_W1 - M0_BASE,          matched DOM_W1_SUPPORT
M_PRF - M0_BASE,             matched PROFILE_F11_SUPPORT
B_PRICE+F11 - B_PRICE,       matched PROFILE_F11_SUPPORT
M_ALL_W5 - M_ALL_W1,         matched COMBINED_W5_SUPPORT
M_ALL_W30 - M_ALL_W5,        matched COMBINED_W30_SUPPORT
```

Ninguno puede rescatar el primary. Ninguno se reporta como hallazgo si el
primary falla.

## 10. Regla terminal

```text
falla cualquier gate primary  ->  NO_EXPANSION_SIGNAL_CLOSE_G1
pasan todos                   ->  DISCOVERY_ONLY_SIGNAL_EXPANSION
```

Un PASS **no** abre validation ni holdout, y **no** autoriza operar. Sólo
autoriza la replicación era-blind de la sección 12.

## 11. Presupuesto de error tipo I sobre la matriz F3

La matriz F3 es una muestra fija de 2727 eventos en 104 sesiones. Cada
hipótesis evaluada sobre ella consume error tipo I. Sin un presupuesto
declarado, la matriz se convierte en una máquina de p-hacking y la sexta
hipótesis "positiva" será ruido con buena cara.

Registro vivo:

| # | Hipótesis | Fecha | Veredicto |
|---|---|---|---|
| 1 | F5 dirección, régimen 3 clases | 2026-07-28 | NO_DISCOVERY_SIGNAL_CLOSE_LINE |
| 2 | G1 expansión, binario | 2026-07-28 | NO_EXPANSION_SIGNAL_CLOSE_G1 |
| 3 | libre | | |
| 4 | libre | | |
| 5 | libre | | |

Reglas del presupuesto:

- máximo **5** hipótesis primary sobre esta matriz;
- agotadas las 5, se exige muestra nueva antes de cualquier otra pregunta;
- cada hipótesis se prerregistra **antes** de mirar su target;
- una hipótesis abandonada a medias cuenta igual que una ejecutada;
- el contador se actualiza en este documento, no en el chat.

## 12. Replicación era-blind obligatoria si G1 pasa

La matriz cubre 2022. Un PASS en G1 significa exclusivamente "hay señal en
2022", que es una afirmación débil dado el historial de esta investigación:
edges que sobreviven un año y mueren al siguiente.

Por tanto, si G1 pasa:

1. no se opera nada;
2. se extrae la misma matriz F3, con el mismo extractor congelado, sobre
   sesiones con depth de 2023 en adelante;
3. se aplican el modelo y los gates sin reajustar ni un parámetro;
4. sólo un PASS también fuera de 2022 convierte esto en candidato.

Si el extractor no puede correr fuera de 2022 por falta de depth, G1 queda como
hallazgo no replicable y no avanza.

## 13. Prohibiciones

- No mirar resultados de G1 antes de congelar el código.
- No usar los resultados direccionales de F5 para orientar nada de G1.
- No reintroducir la dirección por ninguna vía.
- No cambiar umbral, horizonte, ventanas, folds, semillas ni gates.
- No excluir sesiones, ni imputar, ni LOCF.
- No usar sensitivity como rescate.
- No abrir validation ni holdout.
- No reinterpretar un delta negativo como "casi".

## 14. Procedimiento antes de ejecutar

1. implementar el encoder binario y la BBLL, sin tocar el código F5 congelado;
2. tests sintéticos del target binario, de la métrica balanceada, de los pesos
   de clase binarios y de que `AMBIGUOUS` nunca llega al modelo;
3. code review externo de Gemini;
4. freeze con hash de código y de este documento;
5. una única ejecución;
6. auditoría conjunta del resultado.

Veredicto externo solicitado antes de implementar:

```text
GEMINI_G1_PREREGISTRATION: PASS o FAIL
```
