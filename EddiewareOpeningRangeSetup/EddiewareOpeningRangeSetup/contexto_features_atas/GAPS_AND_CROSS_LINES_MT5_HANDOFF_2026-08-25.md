# Handoff técnico — Gaps and Cross Lines (MT5 / IC Markets)

Fecha del handoff: 2026-08-25/26  
Usuario/terminal: IC Markets MT5, cuenta Hedge, terminal `ICMarketsSC-MT5-2`  
Símbolo operado: `USTEC`  
Símbolo de referencia: `SPY.NYSE`  
Timeframe: M1

## 1. Objetivo y límites autorizados

El usuario quiere un EA **exclusivamente visual** para localizar y revisar
discrepancias entre USTEC y SPY.NYSE llamadas “GAPs and Cross Lines”.

Límites expresos del usuario:

- Solo se puede controlar/manipular MT5 para instalar el EA, aceptar ventanas
  de configuración, dibujar en gráficos y navegar por las detecciones.
- Está prohibido abrir, modificar o cerrar operaciones.
- `SPY.NYSE` se usa únicamente como referencia para obtener GAPs y Cross
  Lines.
- Solo se opera conceptualmente en `USTEC`.
- El código entregado no importa ni llama `CTrade`, `OrderSend`, posiciones,
  órdenes ni ninguna función de ejecución.
- No controlar ATAS. El usuario decidió que la primera validación sea solo
  MT5. Cualquier rama ATAS previa quedó descartada.
- Se permite pulsar “Aceptar” en popups/configuración de MT5, nunca en una
  confirmación de orden.

## 2. Definición actual del setup

Todas las velas deben existir simultáneamente en USTEC M1 y SPY.NYSE M1. El
inner join de ambos feeds excluye de forma natural el Overnight de USTEC,
porque SPY.NYSE no imprime velas negociadas durante ese periodo.

### 2.1 Detección del GAP LONG

Se comparan dos velas consecutivas `prev` y `curr`:

1. USTEC y SPY.NYSE: `prev` alcista y `curr` bajista.
2. Cobertura de cuerpo:

   ```text
   coverage = longitud(intersección cuerpo_curr, cuerpo_prev)
              / longitud(cuerpo_prev)
   ```

3. `SPY coverage >= 45%`.
4. `USTEC coverage <= 25%`.
5. `SPY coverage - USTEC coverage >= 25 puntos porcentuales`.
6. El GAP LONG de USTEC es:

   ```text
   lower = low de la vela previa
   upper = low de la vela actual
   ```

7. Se exige `upper - lower >= 1 paso observado de USTEC` (0.1 en este feed).

### 2.2 Detección del GAP SHORT

Regla simétrica:

1. En ambos instrumentos: `prev` bajista y `curr` alcista.
2. Mismos filtros de cobertura.
3. GAP SHORT de USTEC:

   ```text
   lower = high de la vela actual
   upper = high de la vela previa
   ```

### 2.3 Regla corregida sobre penetraciones previas

La primera versión eliminaba un GAP si USTEC penetraba la zona antes de que se
descubriera el objetivo. Eso generó el cuello de botella mencionado al usuario:
521 GAPs brutos, de los cuales 505 eran descartados antes de vincular una
salida.

La regla corregida **no elimina** un GAP por esa penetración. Para asociar un
objetivo cuando existen varios GAPs de la misma dirección:

1. Se priorizan GAPs que todavía estaban limpios en el instante causal del
   objetivo.
2. Después se consideran los GAPs ya tocados.
3. Dentro de cada grupo se prioriza el más reciente.
4. Esta prioridad es solo un desempate; un toque previo no elimina la
   detección del inventario ni introduce lookahead.

Esta prioridad es indispensable para reproducir el ejemplo: a las 22:01 había
un GAP LONG más reciente (21:38) ya penetrado; el GAP limpio correcto era el de
21:27.

### 2.4 Cross Line / objetivo LONG

Después del GAP se busca un par de pivotes máximos USTEC/SPY con fuerza 2 y
desfase máximo de 3 barras. El objetivo queda confirmado cuando:

1. Hay una pareja de reversión alcista→bajista en ambos instrumentos (opción
   activada por defecto).
2. SPY retestea su máximo-pivote dentro de 4 pasos observados de SPY = 0.04.
3. USTEC queda al menos 10 pasos observados = 1.0 por debajo de su
   máximo-pivote equivalente.
4. La mecha máxima pendiente de USTEC se convierte en el target LONG.

Para SHORT se aplica la inversa en mínimos.

### 2.5 Entrada, stop y resultado

- La entrada se estudia solo **después** de confirmar causalmente el objetivo.
- Entrada = 50% exacto del GAP:

  ```text
  entry = lower + 0.5 * (upper - lower)
  ```

- Se acepta medio tick de tolerancia únicamente para representar un midpoint
  que queda entre dos precios negociables (por ejemplo 29140.35 con tick 0.1
  y un low observado de 29140.4).
- Stop provisional del backtest = borde opuesto del GAP, sin buffer.
- Target = mecha pendiente de USTEC definida por la discrepancia posterior.
- Si target y stop aparecen dentro de la misma M1 se cuenta
  conservadoramente como pérdida ambigua.
- Si el target se llena después de confirmarse pero antes de que regrese al
  50%, se registra `TARGET_FILLED_BEFORE_ENTRY` y no hay entrada.
- Los límites por defecto son 180 barras GAP→objetivo, 180 objetivo→entrada y
  360 entrada→salida, siempre dentro de la misma sesión NY.

El stop no fue definido por el usuario; por eso WR, RR y Profit Factor deben
presentarse como **métricas provisionales bajo ese supuesto**, no como
rendimiento definitivo de la idea.

## 3. Ejemplo canónico validado — 2026-08-25

Las horas siguientes son las que muestra el servidor de IC Markets durante
DST (UTC+3).

### 3.1 GAP de entrada

USTEC:

```text
21:26  O 29137.2  H 29146.4  L 29137.0  C 29145.2  (alcista)
21:27  O 29145.4  H 29148.2  L 29143.7  C 29144.2  (bajista)
Cobertura de cuerpo: 12.5%
GAP LONG: [29137.0, 29143.7]
Midpoint: 29140.35
```

SPY.NYSE:

```text
21:26  O 764.80  H 764.94  L 764.79  C 764.94  (alcista)
21:27  O 764.94  H 764.98  L 764.86  C 764.86  (bajista)
Cobertura de cuerpo: 57.1429%
Diferencia: 44.6429 puntos porcentuales
```

### 3.2 Cross Line / salida

```text
Pivote SPY:       21:46, high 765.86
Pivote USTEC:     21:48, high 29201.7
Confirmación:     22:01
Retesteo SPY:     765.83, prácticamente igual al pivote 765.86
Retesteo USTEC:   29193.0, inferior al pivote 29201.7
Target USTEC:     29201.7
```

### 3.3 Secuencia simulada

```text
GAP:       21:27
Objetivo:  22:01
Entrada:   primer toque del 50% a las 22:20
Salida:    target a las 22:53
Resultado: WIN
RR bajo stop en 29137.0: 18.3134R
```

Validador reproducible:

```powershell
cd "C:\Users\k_99_\Documents\Indicador ATAS\mt5_gaps_cross_lines"
python validate_example_20260825.py
```

Salida esperada:

```text
OK: GAP 21:27 -> objetivo 22:01 -> entrada 50% 22:20 -> WIN 22:53 (18.31R)
```

## 4. Hora del servidor y DST

Se verificó que los enteros `time` devueltos por el módulo Python de MT5 están
codificados con la hora de pared del servidor. Durante la temporada DST 2026
de EE. UU., IC Markets usa UTC+3.

Ejemplo observado:

```text
raw MT5 interpretado como UTC: 2026-08-26 04:01
UTC real:                      2026-08-26 01:01
diferencia:                    +3 horas
```

El backtest ahora:

1. Desplaza +3 h las fechas reales UTC usadas en `copy_rates_range`.
2. Conserva `time_broker` para reproducir lo que se ve en MT5.
3. Resta 3 h para obtener `time` UTC real.
4. Convierte ese UTC real a `America/New_York` para fecha de sesión, semana y
   mes.

En el EA MQL5 no hay conversión: `CopyRates` de ambos símbolos ya usa la misma
hora del servidor. El inicio por defecto del navegador es
`NavigatorStartServer = 2026.03.08 10:00`, equivalente a la transición DST
real 2026-03-08 07:00 UTC.

## 5. Archivos principales

Proyecto fuente:

```text
C:\Users\k_99_\Documents\Indicador ATAS\mt5_gaps_cross_lines
```

Archivos:

- `GapsAndCrossLinesNotifier.mq5`: EA visual, comparador y navegador.
- `GapsAndCrossLinesNotifier.ex5`: binario compilado.
- `backtest_gaps_cross_lines.py`: backtest causal MT5-only.
- `validate_example_20260825.py`: aserciones del ejemplo canónico.
- `README.md`: instalación y regla resumida.
- `outputs\dst_2026\gaps.csv`: GAPs brutos.
- `outputs\dst_2026\setups.csv`: setups con objetivo y resultado.
- `outputs\dst_2026\frequency_daily.csv`.
- `outputs\dst_2026\frequency_weekly.csv`.
- `outputs\dst_2026\frequency_monthly.csv`.
- `outputs\dst_2026\summary.json`.
- `outputs\dst_2026\report.md`.

Instalación de MT5:

```text
C:\Users\k_99_\AppData\Roaming\MetaQuotes\Terminal\010E047102812FC0C18890992854220E\MQL5\Experts\Advisors\GapsAndCrossLinesNotifier.mq5
C:\Users\k_99_\AppData\Roaming\MetaQuotes\Terminal\010E047102812FC0C18890992854220E\MQL5\Experts\Advisors\GapsAndCrossLinesNotifier.ex5
```

Compilador:

```text
C:\Program Files\MetaTrader 5 IC Markets Global\MetaEditor64.exe
```

Última compilación antes del handoff: **0 errores, 0 warnings**.

## 6. Arquitectura visual MT5

El mismo EA puede adjuntarse a los dos gráficos:

### 6.1 En USTEC,M1

Muestra únicamente niveles de USTEC:

- Rectángulo del GAP LONG/SHORT.
- Línea punteada del 50%.
- Stop provisional en el borde opuesto.
- Línea de target en la mecha pendiente USTEC.
- Flechas de setup listo, entrada y salida si existen.
- Línea vertical del GAP seleccionado.

### 6.2 En SPY.NYSE,M1

Es exclusivamente una vista de referencia, sin niveles operables:

- Rectángulo sobre el solapamiento de cuerpos del par de velas comparado.
- Etiqueta `SPY cobertura vs USTEC cobertura`.
- Línea del pivote SPY.
- Flecha/etiqueta del retesteo SPY.
- Línea vertical del mismo GAP seleccionado.

El envío de eventos se ejecuta solo cuando `_Symbol == TradeSymbol`, por lo
que adjuntar el EA también a SPY no duplica Telegram.

### 6.3 Navegador limpio

Botones:

```text
< GAP     GAP >
```

Por defecto `ShowOnlySelectedGap=true`. Solo se dibuja el GAP seleccionado y
su setup; los otros aparecen al navegar. Esto se añadió después de observar
que dibujar todo el histórico dejaba el gráfico inutilizable.

La ficha superior contiene:

- posición `n/total`;
- ID;
- fecha/hora servidor;
- dirección;
- rango y 50% en USTEC;
- coberturas USTEC/SPY;
- estado (`SIN OBJETIVO`, `ESPERA 50%`, `CERRADO/WIN`, etc.);
- estado `SPY ACTIVO` o `SPY CERRADO`.

`ShowStatusPanel=false` por defecto para evitar superponer texto con otros
indicadores del usuario. La información indispensable queda en una sola línea
del navegador.

## 7. Backtest MT5-only de la temporada DST 2026 hasta 2026-08-25

Comando usado:

```powershell
python backtest_gaps_cross_lines.py `
  --end 2026-08-26T01:30:00Z `
  --output outputs\dst_2026
```

Datos emparejados:

```text
Periodo UTC real: 2026-03-08 07:00 a 2026-08-26 01:30
Barras M1 emparejadas: 44,842
Días activos: 118
Semanas activas: 25
Meses incluidos: 6 (marzo parcial, agosto parcial)
```

Embudo calculado con el ranking “limpio primero, tocado después”:

```text
GAPs brutos:                           521
GAPs con primer objetivo vinculado:   220
Setups con recompensa positiva:       139
Entradas que tocaron el 50% después:   61
```

Frecuencia:

```text
Setups listos:    1.18/día | 5.56/semana | 23.17/mes incluido
Entradas al 50%:  0.52/día | 2.44/semana | 10.17/mes incluido
```

Entradas por mes:

| Mes | Días activos | Setups listos | Entradas 50% | W | L |
|---|---:|---:|---:|---:|---:|
| 2026-03 (parcial desde DST) | 17 | 9 | 3 | 0 | 3 |
| 2026-04 | 21 | 20 | 7 | 0 | 7 |
| 2026-05 | 20 | 30 | 9 | 2 | 7 |
| 2026-06 | 21 | 21 | 12 | 0 | 12 |
| 2026-07 | 22 | 28 | 11 | 0 | 11 |
| 2026-08 (parcial hasta día 25) | 17 | 31 | 19 | 1 | 18 |

Los meses completos abril-julio tienen al menos 7 entradas; por tanto se
supera la expectativa del usuario de al menos 4 por mes en el peor caso
completo.

Métricas provisionales con stop en el borde opuesto:

```text
Entradas resueltas:        61
Wins/Losses:               3 / 58
WR:                        4.9180%
RR planificado promedio:   21.5882R
RR planificado mediana:     8.2581R
Expectativa observada:     -0.3910R/entrada
Gross profit:              34.1499R
Gross loss:                58.0000R
Profit Factor:              0.5888
```

Estas cifras no deben optimizarse para “verse bien”. El resultado bajo ese SL
es pobre y debe informarse honestamente. El RR promedio se infla por GAPs muy
estrechos; la mediana es más representativa. La siguiente decisión de diseño
debe ser que el usuario defina el stop real antes de juzgar el edge.

## 8. Telegram

Credenciales existentes (no copiar su contenido a documentación ni logs):

```text
C:\Users\k_99_\AppData\Roaming\MetaQuotes\Terminal\Common\Files\telegram_credentials.txt
```

Formato esperado:

```text
token=...
chat_id=...
```

Para WebRequest del EA, MT5 necesita tener autorizada:

```text
https://api.telegram.org
```

El script Python acepta `--send-telegram`. Antes de enviar, terminar la
validación visual emparejada descrita en el checklist inferior. El mensaje
debe indicar que reemplaza un reporte provisional anterior que todavía usaba
la regla errónea de invalidación temprana.

El texto ya generado por `telegram_text(summary)` incluye:

- embudo GAP→objetivo→setup→entrada 50%;
- frecuencia de setups listos;
- frecuencia de entradas 50%;
- entradas por mes;
- W/L, WR;
- RR promedio y mediana;
- expectativa y Profit Factor;
- supuesto de stop;
- solo MT5, SPY activo y Overnight excluido.

Nunca imprimir el token ni el chat_id en consola.

## 9. Estado exacto de MT5 después de la validación del ejemplo

La reproducción canónica pedida por el usuario quedó completada:

- Adjuntar el EA a USTEC y SPY.NYSE.
- Ambos navegadores muestran el mismo inventario de 520 GAPs cerrados en ese
  instante y usan el mismo ID/hora en ambos gráficos.
- Navegar ambos al ejemplo `#519`, hora de servidor `2026.08.25 21:27`.
- En SPY se veía `USTEC 12.5% vs SPY 57.1%`.
- En USTEC se veía la zona `[29137.0, 29143.7]` y midpoint `29140.35`.
- La vista limpia muestra únicamente el GAP seleccionado y su setup; al pulsar
  anterior/siguiente se borran los objetos del GAP previo y se redibuja el
  nuevo ID sin recalcular el histórico.
- El usuario revisó la reproducción y confirmó: “super por lo que vi ya te
  salió”, autorizando continuar el backtest hacia atrás.

Captura anterior con exceso de objetos (solo para historial):

```text
C:\Users\k_99_\Documents\Indicador ATAS\mt5_example_2127_paired.png
```

Captura limpia sincronizada del GAP 21:27:

```text
C:\Users\k_99_\Documents\Indicador ATAS\mt5_example_2127_clean_paired.png
```

Captura limpia ampliada para incluir la secuencia posterior y el
pivote/retest de SPY:

```text
C:\Users\k_99_\Documents\Indicador ATAS\mt5_example_2127_full_clean.png
```

La última fuente y el binario están compilados con 0 errores/0 warnings,
copiados a `MQL5\Experts\Advisors` y cargados en ambos gráficos. El usuario
permitió pulsar “Sí/Aceptar” en popups de reemplazo/configuración de MT5. No se
tocó ningún botón de compra/venta ni se llamó código de ejecución.

El backtest MT5-only final se volvió a lanzar después de completar la
reproducción, con rango `2026-03-08 07:00 UTC` a `2026-08-26 01:30 UTC` y
salida `outputs\dst_2026`. Terminó correctamente y confirmó sin cambios:
521 GAPs, 220 objetivos, 139 setups operables, 61 entradas al 50%, 3W/58L,
WR 4.9%, RR promedio 21.59R, RR mediana 8.26R, expectativa -0.39R y Profit
Factor 0.59 bajo el stop provisional en el borde opuesto.

La diferencia 520 del EA vivo frente a 521 del Python se debe auditar antes de
dar por cerrada la equivalencia completa. Es muy probable que sea una frontera
de vela cerrada/inicio de rango, pero no debe asumirse sin comparar los CSV/IDs.
El ejemplo 21:27 sí coincide en valores, hora y secuencia.

## 10. Checklist concreto para continuar

1. Mantener el límite de seguridad: no pulsar Buy/Sell ni manipular órdenes.
2. El ejemplo 21:27 ya está completado; no rehacerlo desde cero.
3. El backtest final ya terminó; conservar `outputs\dst_2026` como baseline.
4. Continuar hacia atrás con `< GAP` en ambos gráficos, manteniendo ID/hora
   sincronizados.
5. Para cada muestra manual, verificar visualmente las coberturas, GAP USTEC y
   pivote/retest SPY. Para el caso canónico ya confirmado:

   ```text
   USTEC: LONG, [29137.0, 29143.7], 50%=29140.35, cobertura 12.5%
   SPY: cobertura 57.1%
   Pivote SPY 765.86, retest 765.83
   Objetivo USTEC 29201.7
   Entrada 22:20, target 22:53
   ```

6. Guardar capturas limpias solamente de casos representativos/discordantes;
   no crear cientos de imágenes innecesarias.
7. Investigar el único GAP de diferencia 520 vs 521:
   comparar `outputs\dst_2026\gaps.csv` contra los tiempos visibles del EA;
   revisar inclusión de la última vela cerrada y el inicio
   `NavigatorStartServer`.
8. Si cualquier revisión manual exige cambiar la lógica, ejecutar el backtest
   otra vez, correr el validador canónico y recompilar con 0/0.
9. Enviar por Telegram el mensaje final, señalando que sustituye el reporte
    provisional anterior.
10. Informar al usuario de las muestras revisadas hacia atrás, sin afirmar que
    520 casos fueron verificados manualmente si solo se auditaron muestras.

## 11. Verificaciones y comandos útiles

Compilar:

```powershell
$source = 'C:\Users\k_99_\Documents\Indicador ATAS\mt5_gaps_cross_lines\GapsAndCrossLinesNotifier.mq5'
$log = 'C:\Users\k_99_\Documents\Indicador ATAS\mt5_gaps_cross_lines\compile.log'
Start-Process `
  -FilePath 'C:\Program Files\MetaTrader 5 IC Markets Global\MetaEditor64.exe' `
  -ArgumentList @('/compile:' + ('"' + $source + '"'), '/log:' + ('"' + $log + '"')) `
  -WindowStyle Hidden -Wait
Get-Content -LiteralPath $log -Tail 20
```

Validar ejemplo:

```powershell
cd "C:\Users\k_99_\Documents\Indicador ATAS\mt5_gaps_cross_lines"
python -m py_compile backtest_gaps_cross_lines.py validate_example_20260825.py
python validate_example_20260825.py
```

Recalcular backtest:

```powershell
python backtest_gaps_cross_lines.py `
  --end 2026-08-26T01:30:00Z `
  --output outputs\dst_2026
```

Instalar binario/fuente:

```powershell
$install = 'C:\Users\k_99_\AppData\Roaming\MetaQuotes\Terminal\010E047102812FC0C18890992854220E\MQL5\Experts\Advisors'
Copy-Item -LiteralPath '.\GapsAndCrossLinesNotifier.mq5' -Destination $install -Force
Copy-Item -LiteralPath '.\GapsAndCrossLinesNotifier.ex5' -Destination $install -Force
```

## 12. Notas de implementación importantes

- El EA es un Expert Advisor solo porque MQL5 bloquea `WebRequest` desde un
  indicador. No contiene trading.
- El análisis se ejecuta en `OnTimer` cuando hay nueva vela cerrada de SPY.
- `LoadPairedClosedBars` hace merge temporal exacto de USTEC/SPY.
- El dibujo usa prefijo `GCL_` y `ObjectsDeleteAll(0, PREFIX)`, por lo que solo
  borra sus propios objetos.
- El navegador mantiene copias globales de `GapState[]` y `SetupState[]`.
- `OnChartEvent` atiende exclusivamente los dos botones del navegador.
- En SPY, el EA solo dibuja la cobertura y el pivote/retest de referencia.
- En USTEC, dibuja únicamente niveles USTEC.
- `NotifyNewEvents` solo se llama cuando `_Symbol == TradeSymbol`.
- El midpoint usa tolerancia de `0.500001 * TradePriceStep` para evitar errores
  binarios y representar niveles entre ticks.
- Los CSV guardan UTC real y columnas `*_broker` para comparación visual.
- La función antigua conceptualmente llamada invalidación ahora solo clasifica
  `touched_before_target`; no descarta GAPs.

Fin del handoff.
