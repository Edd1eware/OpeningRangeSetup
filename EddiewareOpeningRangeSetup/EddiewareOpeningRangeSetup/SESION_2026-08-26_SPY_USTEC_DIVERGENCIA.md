# Sesión 2026-08-26 — SPY vs USTEC: modo live, auditoría y señal de divergencia

Terminal: IC Markets MT5 `010E047102812FC0C18890992854220E`, cuenta Hedge `7977921`.
Símbolos: `USTEC` (operado) y `SPY.NYSE` (referencia). Timeframe M1.
Proyecto: `C:\Users\k_99_\Documents\Indicador ATAS\mt5_gaps_cross_lines`.

Relojes (crítico para leer cualquier hora de este documento):

| Reloj | Offset | Ejemplo |
|---|---|---|
| Servidor broker | UTC+3 | `2026-08-26 19:47` (lo que se ve en el gráfico) |
| PC local | UTC−6 | `10:47` |
| Sello de deal de `MetaTrader5` en Python | servidor − 6 h | `13:47` → sumar 6 h para hora de servidor |

---

## 1. Resumen ejecutivo

Cinco entregables, en orden de importancia:

1. **Se cerró la auditoría 520 vs 521 GAPs.** Era un error de coma flotante en el EA, no una diferencia de regla. Corregido; EA y backtest de Python ahora coinciden exacto.
2. **Se descubrió que SPY NO adelanta a USTEC en M1.** Correlación de cierres: 0.9128 en el mismo minuto, 0.0044 con SPY adelantado 1 minuto. Cualquier setup que asuma "SPY llega primero" debe justificarse por evento, no por correlación adelantada.
3. **Se calibró la escala SPY→USTEC**: β = 54.2 puntos USTEC por punto SPY (R² 0.83), con deriva mensual fuerte de 42 a 61. Una escala fija se desalinea ~40% entre meses.
4. **Se mecanizó la regla de zonas del usuario y NO tiene edge**: EV −0.047R, PF 0.918 sobre 2196 trades. En cambio, la ingeniería inversa desde los fills reales encontró otra señal (desajuste acumulado de 5 min, z ≤ −3) con +27 pts a 30 min contra +3.2 de base.
5. **El EA quedó en producción** enviando Telegram con captura emparejada USTEC+SPY cuando la vela de SPY convertida a escala USTEC diverge del rango real.

---

## 2. Estado final del EA

`GapsAndCrossLinesNotifier.mq5` — **EA solo visual, no importa `CTrade`, no llama `OrderSend`, no toca órdenes.**
Compilado 0 errores / 0 warnings. Adjunto a `USTEC,M1` y `SPY.NYSE,M1` el 2026-08-26 18:07.

### 2.1 Inputs de la alerta principal (divergencia de vela)

| Input | Valor | Razón |
|---|---|---|
| `AlertOnDiscrepancy` | `true` | Alerta principal |
| `DiscrepancyBigPercent` | `40.0` | Las velas marcadas por el usuario caen en +39.5% a +46.1% |
| `DiscrepancySmallPercent` | `50.0` | Lado contrario (USTEC se quedó corto), ~1.8/día |
| `DiscrepancyLocalMaxBars` | `5` | Con 30 el filtro borraba las propias velas del usuario |
| `DiscrepancyMinReferenceSteps` | `2` | Ignora velas de SPY sin recorrido |
| `MaxZoneAlertsPerHour` | `4` | Sin tope serían 72 avisos/día |
| `EnablePopupAlert` | `false` | El usuario quiere solo Telegram, sin popups de MT5 |
| `SendChartScreenshot` / `PairedScreenshot` | `true` | Álbum USTEC+SPY en un mensaje |

### 2.2 Otros detectores incluidos

| Detector | Input | Estado | Frecuencia |
|---|---|---|---|
| Divergencia de vela (%) | `AlertOnDiscrepancy` | **activo** | ~20-26/día con tope |
| z acumulado 5 min | `AlertOnDivergence`, `DivergenceZAlert=-3.0` | activo | ~4/día |
| Zonas relativas (SPY visitó, USTEC no) | `AlertOnRelativeZones` | **desactivado** | 277 eventos/día, sin edge |
| GAPs y Cross Lines originales | `AlertOnSetupEvents` | desactivado | — |

### 2.3 Formato del mensaje de Telegram

```
GAPS & CROSS LINES | DIVERGENCIA +43%
USTEC EXAGERO EL MOVIMIENTO (vela mas grande)
Hora 2026.08.27 17:26

SP500 rango 0.18 x beta 58.9 = 10.60 implicado
USTEC rango real 15.20
DIFERENCIA +43%

Cierre real 29108.00 vs implicado 29114.75 (-6.75 pts)
Desajuste 5 min z -1.03
Vela bajista | 29107.80 - 29123.00 | 50% 29115.40
```
Más dos fotos: gráfico de USTEC y gráfico de SPY, en el mismo mensaje.

---

## 3. Auditoría 520 vs 521 GAPs — CERRADA

Venía del handoff anterior sin resolver.

**Causa raíz**: el GAP #420 (2026-08-05 22:20, SHORT, `29653.0`–`29653.1`) mide exactamente 1 paso observado. En doble precisión:

```
29653.1 - 29653.0 = 0.09999999999854481
```

El EA comparaba `upper - lower < MinGapSteps * TradePriceStep` = `0.0999... < 0.10` → **verdadero** → descartaba un GAP legítimo. Python usaba `trade_tick_size` real de MT5 (**0.01**, no 0.1), así que no lo descartaba.

**Corrección aplicada** en `DetectGap`:

```mql5
double min_gap = MathMax(0, MinGapSteps) * TradePriceStep;
if(upper - lower < min_gap - 1e-6)
   return false;
```

Verificado: el EA volcó `GCL_ea_gaps.csv` con **521 GAPs**, idéntico al backtest. Antes 520.

**Lección**: cualquier comparación de precios contra un múltiplo de tick necesita epsilon.

---

## 4. Modo live implementado

### 4.1 Funcionalidad

| Función | Detalle |
|---|---|
| Vigilancia por tick | `OnTick` revisa setups vivos contra Bid en curso; la alerta del toque del 50% ya no espera al cierre de la M1 |
| HUD en pantalla | Línea con `z` actual, desajuste en puntos, beta y nivel de entrada pendiente |
| Niveles operables | Horizontales de pantalla completa (entrada / SL / TP) para setups vivos |
| Captura emparejada | La instancia de SPY captura por petición; la de USTEC envía el álbum |
| Dedupe de avisos | `GlobalVariableTemp` por evento; un reescaneo de historia no repite alertas |
| Volcado de inventario | `GCL_ea_gaps.csv` en `MQL5\Files` para auditar contra Python |
| Botón `FOTO TG` | Snapshot manual bajo demanda |

### 4.2 Gotchas técnicos (los más caros de la sesión)

**a) El EA corre en el hilo del gráfico.** `Sleep()` impide que MT5 procese `ChartNavigate` y `ChartRedraw`. La captura se resolvió como máquina de estados sobre `OnTimer`:

```
fase 1: seleccionar GAP, emitir ChartNavigate, ceder control
fase 3: verificar encuadre, ChartRedraw, ceder control
fase 3b: ChartScreenShot
fase 2: esperar acuse de la instancia de SPY, enviar álbum
```

**b) `ChartRedraw()` solo encola el repintado.** Capturar en la misma llamada devuelve el frame anterior. Hay que dejar pasar un tick de timer.

**c) `iBarShift` devuelve −1** mientras la serie del gráfico no está sincronizada tan atrás. Respaldo con `Bars(symbol, tf, target, now) - 1`.

**d) MT5 no recarga el EA al copiar el `.ex5`.** Hay que re-adjuntarlo. Se creó `attach_ea_mt5.py` para automatizarlo:
- Activa el gráfico con `WM_MDIACTIVATE`, **nunca con clic**, para no arriesgar el panel de 1-click trading.
- Acepta el popup de reemplazo y la ventana de propiedades.
- **Adjuntar SPY primero**: debe estar escuchando antes de que USTEC pida la captura emparejada.

**e) Telegram `sendPhoto` y `sendMediaGroup`** requieren multipart/form-data armado byte a byte en MQL5. Coordinación entre instancias vía GlobalVariables (`GCL_shot_request`, `GCL_shot_gap_time`, `GCL_shot_ack`) más los PNG en `MQL5\Files`.

---

## 5. Investigación cuantitativa

Muestra: 45,222 barras M1 emparejadas, 2026-03-09 a 2026-08-26, 119 días activos.
El inner join con SPY excluye el Overnight de USTEC de forma natural.

### 5.1 ¿SPY adelanta a USTEC? **NO**

| Lag | Lectura | corr |
|---|---|---|
| −1 | USTEC adelantado | 0.0149 |
| **0** | **mismo minuto** | **0.9128** |
| +1 | SPY adelantado | 0.0044 |
| +2 | SPY adelantado | −0.0025 |
| +3 | SPY adelantado | −0.0129 |

Todo el acoplamiento vive en el mismo minuto. Si hay adelanto real, es intrabar (segundos) y M1 no lo puede ver.

### 5.2 Escala SPY → USTEC

OLS sobre cambios de cierre M1: **β = 54.158**, R² = 0.8332, n = 45,101.

| Mes | n | β |
|---|---:|---:|
| 2026-03 | 6,443 | 42.44 |
| 2026-04 | 7,953 | 46.19 |
| 2026-05 | 7,580 | 56.43 |
| 2026-06 | 7,959 | 61.16 |
| 2026-07 | 8,344 | 61.18 |
| 2026-08 | 6,822 | 57.84 |

**No usar escala fija.** El ratio de precio (≈38.5) no sirve como factor de movimiento; la mediana móvil del cociente de rangos da ≈63.8, distinta del β OLS por asimetría de la distribución.

### 5.3 Niveles de SPY que USTEC no cubrió

Proyectando el high/low de SPY con β, anclado al cierre del mismo minuto:

| Faltante ≥ | n | por día | % llenado en 60 min | mediana min |
|---|---:|---:|---:|---:|
| 5 pts | 3,618 | 30.40 | 77.4% | 4 |
| 10 pts | 555 | 4.66 | 66.3% | 5 |
| 20 pts | 53 | 0.45 | 35.9% | 11 |

Falta control de azar para saber si el 66% supera al ruido.

### 5.4 Regla de zonas relativas del usuario — **SIN EDGE**

Regla mecanizada: vela ancla A con extremo; vela posterior B (≤15 min) **visita ese nivel en SPY pero no en USTEC**; la banda que USTEC dejó sin visitar es la zona (arriba = imán/TP, abajo = entrada). Solo vive la más reciente sin rellenar por lado. Imán arriba obligatorio. Stop bajo el mínimo del swing previo.

Resultado sobre 119 días, banda mínima 5 pts, **sin costes**:

| Mes | trades | W | L | WR % | RR med | PF | EV (R) | total R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-03 | 258 | 86 | 172 | 33.33 | 2.10 | 0.841 | −0.106 | −27.3 |
| 2026-04 | 177 | 87 | 90 | 49.15 | 1.45 | 1.506 | +0.257 | +45.5 |
| 2026-05 | 337 | 185 | 152 | 54.90 | 1.15 | 1.441 | +0.199 | +67.1 |
| 2026-06 | 506 | 184 | 322 | 36.36 | 1.47 | 0.598 | −0.256 | −129.4 |
| 2026-07 | 586 | 219 | 367 | 37.37 | 1.35 | 0.628 | −0.233 | −136.4 |
| 2026-08 | 332 | 169 | 163 | 50.90 | 1.19 | 1.468 | +0.230 | +76.3 |
| **TOTAL** | **2196** | 930 | 1266 | **42.35** | 1.38 | **0.918** | **−0.047** | **−104.3** |

Breakeven WR con RR 1.39 = **41.84%**. El sistema está en 42.35% → empatado con el azar. t = −1.51. Meses alternan +0.26 / −0.26 sin patrón.

Nota: la penetración de SPY en el ejemplo del usuario fue de **1 tick (0.01)**, así que el tamaño del exceso no sirve como filtro. La regla tal cual dispara ~234 candidatas/día por lado.

---

## 6. Ingeniería inversa desde los fills reales

Punto de inflexión de la sesión: en vez de mecanizar la **descripción** del setup, se reconstruyó desde los **fills**.

### 6.1 Operativa real del 2026-08-26 (hora de servidor)

| # | Entrada | Precio | Vol | Salidas | Resultado |
|---|---|---:|---:|---|---:|
| 1 | 17:25:18 | 29134.1 | 0.1 | SL 17:27:01 @29099.1 | −3.50 |
| 2 | 17:27:19 + 17:28:23 | 29107.0 / 29100.1 | 0.1 + 0.5 | 17:55 @29174.2 · 17:58 @29176.7 · 18:01 @29183.0 | **+46.28** |
| 3 | 19:47:44 + 19:48:11 | 29122.7 / 29126.2 | 0.5 + 0.5 | 19:59 @29143.8 · 20:15 @29176.6 (tp) | **+35.75** |
| 4 | 22:52:54 | 29243.7 | 0.5 | SL 22:53:10 @29235.6 | −4.05 |
| 5 | 23:00:22 | 29238.8 | 0.5 | 23:04 @29269.7 · 23:05 @29291.4 (tp) | **+19.79** |

**Neto del día: +94.27 USD.** Todas las entradas fueron manuales (magic = 0).

### 6.2 Hallazgo que rompió la hipótesis de zonas

| Fill | Zona de entrada viva | Imán | Resultado |
|---|---|---|---|
| 17:25 | ninguna | a 106 pts | SL |
| 17:27 | **ninguna** | a 133 pts | ganador |
| 17:28 | **ninguna** | a 140 pts | ganador |
| 19:47 | **ninguna** | ninguna | ganador |
| 19:48 | [29114.3–29119.0], fill 7.2 pts arriba | ninguna | ganador |
| 22:52 | ✓ presente + imán ✓ | ✓ | **SL** |

**El único fill que encajaba perfecto en la lógica de zonas fue el perdedor.** Los ganadores no tenían zona viva. La secuencia #2 sí cerró dentro de la TP zone dibujada a mano (29181.39/29188.10), así que el imán como objetivo sí funcionó; lo que no funcionó fue la zona como gatillo de entrada.

---

## 7. La señal que sí apareció: desajuste acumulado (z)

Definición, en puntos de USTEC:

```
spread_k(t) = (USTEC_t − USTEC_{t−k}) − β · (SPY_t − SPY_{t−k})
z_k(t)      = (spread_k − media móvil 240) / desviación móvil 240
```

β rodante 120 barras, desplazada una barra (ninguna barra se calibra a sí misma).
Negativo = USTEC cayó más de lo que SPY justifica.

### 7.1 Separa los fills del usuario

| Fill | z_1m | z_3m | z_5m | Resultado |
|---|---:|---:|---:|---|
| 17:25 | +0.65 | **+1.26** | +0.29 | SL |
| 17:27 | −0.45 | **−1.03** | −0.21 | WIN |
| 17:28 | −0.07 | **−1.55** | −0.91 | WIN |
| 19:47 | +0.58 | +0.52 | +0.57 | WIN |
| 19:48 | −0.23 | +0.20 | +0.04 | WIN |
| 22:52 | **+1.69** | +0.63 | +0.38 | SL |

**Las dos pérdidas fueron las únicas con z claramente positivo.** Seis casos no son prueba, pero es el mejor separador que salió de datos reales.

### 7.2 Movimiento posterior por tramo de z (119 días)

| z_5 | n | +5m | +15m | +30m | %sube 30m |
|---|---:|---:|---:|---:|---:|
| **≤ −3** | 490 | **+9.50** | **+18.63** | **+27.45** | **59.6%** |
| −3 a −2 | 846 | +2.30 | +6.74 | +10.71 | 54.9% |
| −2 a −1 | 3,824 | −0.43 | +2.06 | +6.93 | 53.5% |
| −1 a +1 | 34,916 | +0.23 | +1.16 | +1.77 | 52.0% |
| **Base** | 45,132 | +0.52 | +1.56 | +3.11 | 52.4% |

Monótono al bajar el z. z ≤ −3 da 9× la base a 30 minutos, con ~4 señales/día.

### 7.3 Desglose mensual — LA ADVERTENCIA

| Mes | n | +15m | +30m | %sube 30m | base +30m |
|---|---:|---:|---:|---:|---:|
| 2026-03 | 57 | +29.3 | +37.2 | 68.4% | −2.0 |
| 2026-04 | 83 | +9.8 | +18.9 | 56.6% | +14.0 |
| 2026-05 | 78 | +22.8 | +28.6 | 61.5% | +10.5 |
| 2026-06 | 93 | +65.1 | **+85.5** | 74.2% | −1.5 |
| 2026-07 | 94 | −14.9 | −5.6 | 56.4% | −5.5 |
| 2026-08 | 85 | +2.5 | +1.2 | **42.4%** | +3.8 |
| **TOTAL** | 490 | +18.6 | **+27.45** | 59.6% | +3.25 |

t = 4.02 contra la base, **pero**:
- **Junio (+85.5) infla el total.** Es el mes atípico que sesga cualquier optimización.
- **Agosto está muerto**: +1.2 pts con 42.4% de aciertos, peor que la base (50.7%).
- Cuatro meses buenos, dos planos. No es edge confirmado; es la señal más fuerte encontrada, nada más.

---

## 8. Divergencia de vela individual (lo que dispara el Telegram)

Vela de SPY convertida a escala USTEC, comparada contra la vela real del mismo minuto:

```
implicado_rango = (high_SPY − low_SPY) × β
diferencia_%    = (rango_real_USTEC − implicado_rango) / implicado_rango × 100
implicado_cierre = open_USTEC + (close_SPY − open_SPY) × β
```

### 8.1 Calibración con las velas marcadas por el usuario

| Minuto | Rango real | Rango implícito | **Dif %** | Cierre vs implícito |
|---|---:|---:|---:|---:|
| 17:26 (ganador) | 15.2 | 10.6 | **+43.4%** | **−6.75** |
| 17:27 (ganador) | 13.1 | 13.6 | −3.8% | **−3.52** |
| 18:52 (ancla del ejemplo) | 17.2 | 12.3 | **+39.5%** | −1.54 |
| 19:47 (ganador) | 13.8 | 9.7 | **+42.6%** | +3.45 |
| 19:48 (ganador) | 9.7 | 6.6 | **+46.1%** | −0.64 |
| 22:52 (perdedor) | 15.4 | 18.6 | −17.4% | **+1.00** |

Las velas del usuario caen en **+39% a +46%**. De ahí el umbral 40%.

### 8.2 ADVERTENCIA sobre el signo

Como disparo de compra, el % de **una sola vela** apunta al lado contrario:

| Filtro | n/día | +15m | +30m | %sube |
|---|---:|---:|---:|---:|
| dif ≥40% y cierre ≤ −5 pts | 16.24 | −3.2 | **−7.5** | 49.9% |
| dif ≥60% y cierre ≤ −8 pts | 6.52 | −7.6 | **−16.1** | 47.4% |
| Base | — | +1.56 | +3.11 | 52.4% |

**Vela grande de USTEC que cierra por debajo de lo implícito → sigue cayendo, no rebota.** Lo que rebotaba era el z acumulado de 5 minutos. Son dos cosas distintas; por eso el mensaje de Telegram lleva **ambos números** y la decisión queda en el operador.

### 8.3 Control de frecuencia

| Umbral | Ventana máx. local | Alertas/día | ¿Dispara en las velas del usuario? |
|---|---:|---:|---|
| 40% | 0 (sin filtro) | 72.1 | 17:26, 19:47, 19:48 |
| **40%** | **5** | **36.8** | **17:26, 19:47, 19:48** |
| 40% | 10 | 23.8 | solo 19:47, 19:48 |
| 40% | 30 | 11.0 | ninguna |
| 60% | 5 | ~24 | — |

Elegido: umbral 40%, ventana 5, tope 4/hora → **≈20-26 alertas/día**.
Si satura: subir `DiscrepancyBigPercent` a 60 desde las propiedades del EA.

---

## 9. Archivos

### 9.1 Nuevos (en `mt5_gaps_cross_lines`)

| Archivo | Función |
|---|---|
| `attach_ea_mt5.py` | Adjunta el EA a ambos gráficos sin clic sobre el gráfico; SPY primero |
| `audit_ea_vs_python_gaps.py` | Compara reglas de sesión NY vs broker (descartó esa hipótesis) |
| `spy_leads_ustec.py` | Lead-lag, β OLS global y mensual, niveles sin llenar |
| `discrepancy_scan.py` | Frecuencia de discrepancia por tamaño con escala de mediana móvil |
| `spy_discrepancy_setup.py` | Primer detector de niveles implicados |
| `relative_discrepancy.py` | Detector de zonas relativas + simulación con tabla mensual |
| `reverse_from_fills.py` | Reconstruye el contexto SPY/USTEC de cada fill real |
| `divergence_signal.py` | Spread, z y movimiento posterior por tramo |

### 9.2 Modificado

`GapsAndCrossLinesNotifier.mq5` — epsilon en `DetectGap`, modo live, captura emparejada por máquina de estados, detector de divergencia, detector de zonas relativas, HUD, botón `FOTO TG`, volcado de inventario.

### 9.3 Salidas

```
outputs\dst_2026\        baseline anterior (GAPs, setups, ticks)
outputs\spy_lead\        lead-lag y niveles sin llenar
outputs\relative_b5\     eventos y trades de zonas relativas
outputs\spy_setup\       niveles implicados
```

---

## 10. Comandos

Compilar y desplegar:

```powershell
$src = 'C:\Users\k_99_\Documents\Indicador ATAS\mt5_gaps_cross_lines'
Start-Process -FilePath 'C:\Program Files\MetaTrader 5 IC Markets Global\MetaEditor64.exe' `
  -ArgumentList @('/compile:"' + $src + '\GapsAndCrossLinesNotifier.mq5"', '/log:"' + $src + '\compile.log"') `
  -WindowStyle Hidden -Wait
Get-Content -LiteralPath "$src\compile.log" | Select-String -Pattern ' error | warning |Result'
$install = 'C:\Users\k_99_\AppData\Roaming\MetaQuotes\Terminal\010E047102812FC0C18890992854220E\MQL5\Experts\Advisors'
Copy-Item -LiteralPath "$src\GapsAndCrossLinesNotifier.mq5" -Destination $install -Force
Copy-Item -LiteralPath "$src\GapsAndCrossLinesNotifier.ex5" -Destination $install -Force
```

Re-adjuntar (obligatorio tras copiar el `.ex5`):

```powershell
cd "C:\Users\k_99_\Documents\Indicador ATAS\mt5_gaps_cross_lines"
python -u attach_ea_mt5.py
```

Verificar:

```powershell
Get-Content -LiteralPath 'C:\Users\k_99_\AppData\Roaming\MetaQuotes\Terminal\010E047102812FC0C18890992854220E\MQL5\Logs\20260826.log' -Tail 20
```

Reproducir los estudios:

```powershell
python -u spy_leads_ustec.py
python -u divergence_signal.py
python -u reverse_from_fills.py --day 2026-08-26
python -u relative_discrepancy.py --start 2026-03-08T07:00:00Z --end 2026-08-27T01:30:00Z --min-band-pts 5 --output outputs/relative_b5
```

---

## 11. Pendientes

| # | Pendiente | Detalle |
|---|---|---|
| 1 | Encuadre de captura histórica | `ChartScreenShot` a veces sale con el borde derecho aunque `CHART_FIRST_VISIBLE_BAR` reporte el gráfico desplazado. No afecta a alertas en vivo (el evento está en el borde derecho) |
| 2 | Control de azar del relleno | El 66% de relleno de niveles ≥10 pts necesita comparación contra toque aleatorio a la misma distancia |
| 3 | Validación forward del z | Julio y agosto salieron planos. Hace falta confirmar en vivo antes de darle peso |
| 4 | Costes | Ningún resultado de este documento descuenta spread ni comisión |
| 5 | Estudio de ticks | El adelanto de SPY, si existe, solo se puede medir con datos de tick de ambos símbolos |

---

## 12. Advertencias metodológicas

1. **Nada de lo medido aquí incluye costes.** El spread de USTEC se come varios puntos por operación.
2. **Junio 2026 sesga todo.** Cualquier optimización sobre la muestra completa está mirando ese mes.
3. **Agosto, el mes más reciente, no confirma ninguna de las dos señales.**
4. **La regla de zonas fue mecanizada desde una descripción verbal**, y falló. La ingeniería inversa desde fills reales fue más productiva: repetir ese método si aparecen setups nuevos.
5. **El EA nunca ejecuta órdenes.** Todas las operaciones registradas el 2026-08-26 fueron manuales del usuario (magic = 0), confirmado por él.
