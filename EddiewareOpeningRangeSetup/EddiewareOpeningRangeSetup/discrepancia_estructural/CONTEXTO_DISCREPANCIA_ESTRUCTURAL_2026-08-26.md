# Discrepancia estructural SPY vs USTEC — contexto completo

Sesión de trabajo: **2026-08-26**
Terminal: IC Markets MT5 `010E047102812FC0C18890992854220E`, cuenta Hedge `7977921`
Símbolos: `USTEC` (operado) · `SPY.NYSE` (referencia) · Timeframe M1
Código: `C:\Users\k_99_\Documents\Indicador ATAS\mt5_gaps_cross_lines`

> Documento hermano, más orientado a la operación del EA:
> `..\SESION_2026-08-26_SPY_USTEC_DIVERGENCIA.md`
> Este archivo es el canónico para **el concepto** de discrepancia estructural.

---

## 0. Relojes — leer antes que nada

| Reloj | Offset | Ejemplo del mismo instante |
|---|---|---|
| Servidor broker (lo que se ve en el gráfico) | UTC+3 | `19:47` |
| PC local | UTC−6 | `10:47` |
| Sello de deal desde Python `MetaTrader5` | servidor − 6 h | `13:47` (sumar 6 h) |
| Nueva York | UTC−4 (DST) | `12:47` |

Sesión cash SPY: 09:30–16:00 NY = **16:30–23:00 servidor**. SPY no cotiza overnight; el inner join de ambos feeds ya excluye ese periodo de forma natural.

---

## 1. La idea, en una frase

> USTEC y SPY deberían moverse igual una vez ajustada la escala. Cuando en el mismo minuto **una hace algo que la otra no**, queda una discrepancia; esa discrepancia es la señal.

Todo el trabajo de esta sesión fue convertir esa frase en algo medible, y después comprobar si contiene ventaja real.

---

## 2. Lo primero que hay que saber: la escala

### 2.1 El ratio de precio NO sirve

| Medida | Valor | Comentario |
|---|---:|---|
| Precio USTEC / precio SPY | ≈ 38.5 | **Incorrecto** como factor de movimiento |
| Mediana móvil del cociente de rangos | ≈ 63.8 | Sobreestima, por asimetría de la distribución |
| **β OLS sobre cambios de cierre M1** | **54.2** | **El correcto.** R² = 0.83, n = 45,101 |

Fórmula operativa:

```
puntos_USTEC = puntos_SPY × β
β = cov(ΔUSTEC, ΔSPY) / var(ΔSPY)   sobre 120 barras previas, desplazada 1
```

### 2.2 β se mueve con el tiempo — nunca fijarla

| Mes | n | β |
|---|---:|---:|
| 2026-03 | 6,443 | 42.44 |
| 2026-04 | 7,953 | 46.19 |
| 2026-05 | 7,580 | 56.43 |
| 2026-06 | 7,959 | 61.16 |
| 2026-07 | 8,344 | 61.18 |
| 2026-08 | 6,822 | 57.84 |

Deriva del 42 al 61 en cinco meses: **44% de diferencia**. Una escala "a ojo" fijada en marzo estaría completamente desalineada en julio. Por eso todo el código usa β rodante.

---

## 3. Hallazgo que rompe la intuición: SPY no adelanta a USTEC

Correlación de cambios de cierre M1, 45,222 barras emparejadas:

| Lag | Lectura | corr |
|---|---|---:|
| −5 | USTEC adelantado | −0.0084 |
| −3 | USTEC adelantado | −0.0099 |
| −1 | USTEC adelantado | +0.0149 |
| **0** | **mismo minuto** | **+0.9128** |
| +1 | SPY adelantado | +0.0044 |
| +2 | SPY adelantado | −0.0025 |
| +3 | SPY adelantado | −0.0129 |
| +5 | SPY adelantado | −0.0107 |

**Todo el acoplamiento vive en el mismo minuto.** No hay ventaja predictiva de SPY sobre USTEC a un minuto vista.

Consecuencia práctica: la narrativa "SPY llega primero y USTEC lo alcanza después" **no se puede sostener con datos M1**. Si ese adelanto existe, ocurre en segundos dentro de la vela, y haría falta datos de tick de ambos símbolos para verlo. Cualquier setup basado en esa premisa debe justificarse **por evento concreto** (un nivel visitado en un feed y no en el otro), no por correlación adelantada.

---

## 4. Las tres formas de medir la discrepancia

Se probaron tres definiciones distintas. Conviene tenerlas separadas porque **apuntan a direcciones contrarias**.

| # | Definición | Fórmula | Resultado |
|---|---|---|---|
| A | **Nivel no visitado** | SPY visita un extremo que USTEC no visita | Sin edge |
| B | **Tamaño de vela** | rango real vs rango implícito, mismo minuto | Continuación (sigue cayendo) |
| C | **Desajuste acumulado** | spread de 5 min contra su propia distribución | Reversión (rebota) |

### 4.1 Definición A — nivel no visitado (la regla verbal del usuario)

Regla mecanizada:
1. Vela ancla A con un extremo o mecha.
2. Vela posterior B (≤15 min) **visita ese nivel en SPY pero no en USTEC**.
3. La banda que USTEC dejó sin visitar es la zona: arriba = imán/TP, abajo = zona de entrada.
4. Solo vive la más reciente sin rellenar por lado; muere al rellenarse o al cerrar sesión.
5. Imán arriba obligatorio. Entrada al primer toque. Stop bajo el mínimo del swing previo.

Ejemplo canónico documentado (2026-08-26, hora servidor):

```
IMÁN    ancla 18:52  máx USTEC 29187.7 / SPY 765.67
        señal 18:56-18:57  SPY 765.73 y 765.75 superan; USTEC 29177.6 no
        -> banda sin visitar 29177.6 .. 29187.7

ENTRADA ancla 19:46  mecha inferior USTEC [29104.2, 29110.2] / SPY [763.94, 764.04]
        señal 19:49  SPY baja a 764.03 (entra en la mecha)
                     USTEC solo baja a 29112.1 (no entra)
        -> zona de entrada 29104.2 .. 29110.2
```

**Resultado sobre 119 días, banda mínima 5 pts, sin costes:**

| Mes | trades | W | L | WR % | RR med | PF | EV (R) | total R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-03 | 258 | 86 | 172 | 33.33 | 2.10 | 0.841 | −0.106 | −27.3 |
| 2026-04 | 177 | 87 | 90 | 49.15 | 1.45 | 1.506 | +0.257 | +45.5 |
| 2026-05 | 337 | 185 | 152 | 54.90 | 1.15 | 1.441 | +0.199 | +67.1 |
| 2026-06 | 506 | 184 | 322 | 36.36 | 1.47 | 0.598 | −0.256 | −129.4 |
| 2026-07 | 586 | 219 | 367 | 37.37 | 1.35 | 0.628 | −0.233 | −136.4 |
| 2026-08 | 332 | 169 | 163 | 50.90 | 1.19 | 1.468 | +0.230 | +76.3 |
| **TOTAL** | **2196** | 930 | 1266 | **42.35** | 1.38 | **0.918** | **−0.047** | **−104.3** |

Breakeven WR con RR 1.39 = **41.84%**; el sistema da 42.35% → **empatado con el azar**. t = −1.51.

Dos detalles que invalidan la regla tal como está enunciada:
- La penetración de SPY en el ejemplo del usuario fue de **1 tick (0.01)**. El tamaño del exceso no puede servir de filtro.
- La regla dispara **~234 candidatas por día y por lado**. La vela ancla 19:46 no destaca ni por tamaño (rango 11.3 real vs 12.8 implícito, −12%) ni por mecha (6.0 vs 5.8). No hay nada objetivo que la distinga de las otras 233.

### 4.2 Definición B — tamaño de vela (lo que dispara el Telegram)

```
implicado_rango  = (high_SPY − low_SPY) × β
diferencia_%     = (rango_real_USTEC − implicado_rango) / implicado_rango × 100
implicado_cierre = open_USTEC + (close_SPY − open_SPY) × β
```

Calibración con las velas que el usuario marcó a mano:

| Minuto (servidor) | Rango real | Rango implícito | **Dif %** | Cierre vs implícito |
|---|---:|---:|---:|---:|
| 17:26 (contexto ganador) | 15.2 | 10.6 | **+43.4%** | **−6.75** |
| 17:27 (contexto ganador) | 13.1 | 13.6 | −3.8% | **−3.52** |
| 18:52 (ancla del ejemplo) | 17.2 | 12.3 | **+39.5%** | −1.54 |
| 19:47 (contexto ganador) | 13.8 | 9.7 | **+42.6%** | +3.45 |
| 19:48 (contexto ganador) | 9.7 | 6.6 | **+46.1%** | −0.64 |
| 22:52 (perdedor) | 15.4 | 18.6 | −17.4% | **+1.00** |

Las velas marcadas caen en **+39% a +46%**. De ahí el umbral 40% del EA.

**ADVERTENCIA sobre el signo** — como disparo de compra apunta al lado contrario:

| Filtro | n/día | +15m | +30m | %sube |
|---|---:|---:|---:|---:|
| dif ≥40% y cierre ≤ −5 pts | 16.24 | −3.2 | **−7.5** | 49.9% |
| dif ≥60% y cierre ≤ −8 pts | 6.52 | −7.6 | **−16.1** | 47.4% |
| Base (todas las barras) | — | +1.56 | +3.11 | 52.4% |

Vela grande de USTEC que cierra por debajo de lo implícito → **sigue cayendo**, no rebota.

### 4.3 Definición C — desajuste acumulado (la que sí apuntó a rebote)

```
spread_k(t) = (USTEC_t − USTEC_{t−k}) − β · (SPY_t − SPY_{t−k})
z_k(t)      = (spread_k − media_240) / desviación_240
```

Negativo = USTEC cayó más de lo que SPY justifica.

**Movimiento posterior por tramo de z (119 días):**

| z_5 | n | +5m | +15m | +30m | %sube 30m |
|---|---:|---:|---:|---:|---:|
| **≤ −3** | 490 | **+9.50** | **+18.63** | **+27.45** | **59.6%** |
| −3 a −2 | 846 | +2.30 | +6.74 | +10.71 | 54.9% |
| −2 a −1 | 3,824 | −0.43 | +2.06 | +6.93 | 53.5% |
| −1 a +1 | 34,916 | +0.23 | +1.16 | +1.77 | 52.0% |
| ≥ +2 | 1,254 | +0.8 | −1.3 | +12.4 | ≈52% |
| **Base** | 45,132 | +0.52 | +1.56 | +3.11 | 52.4% |

Monótono al bajar el z. z ≤ −3 da **9× la base** a 30 minutos, con ≈4 señales/día.

**Desglose mensual — la advertencia obligatoria:**

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
- **Agosto está muerto**: +1.2 pts con 42.4% de aciertos, por debajo de la base (50.7%).
- Cuatro meses buenos, dos planos. Señal más fuerte encontrada, **no** edge confirmado.

---

## 5. El giro metodológico: ingeniería inversa desde los fills

Mecanizar la **descripción verbal** del setup falló. Reconstruirlo desde los **fills reales** funcionó mucho mejor. Este es el método a repetir cuando aparezca un setup nuevo.

### 5.1 Operativa real del 2026-08-26 (hora servidor)

| # | Entrada | Precio | Vol | Salidas | Resultado |
|---|---|---:|---:|---|---:|
| 1 | 17:25:18 | 29134.1 | 0.1 | SL 17:27:01 @29099.1 | −3.50 |
| 2 | 17:27:19 + 17:28:23 | 29107.0 / 29100.1 | 0.1 + 0.5 | 17:55 @29174.2 · 17:58 @29176.7 · 18:01 @29183.0 | **+46.28** |
| 3 | 19:47:44 + 19:48:11 | 29122.7 / 29126.2 | 0.5 + 0.5 | 19:59 @29143.8 · 20:15 @29176.6 (tp) | **+35.75** |
| 4 | 22:52:54 | 29243.7 | 0.5 | SL 22:53:10 @29235.6 | −4.05 |
| 5 | 23:00:22 | 29238.8 | 0.5 | 23:04 @29269.7 · 23:05 @29291.4 (tp) | **+19.79** |

**Neto: +94.27 USD.** Todas manuales (magic = 0). El EA nunca ejecuta órdenes.

### 5.2 El hallazgo que tumbó la hipótesis de zonas

| Fill | Zona de entrada viva | Imán arriba | Resultado |
|---|---|---|---|
| 17:25 | ninguna | a 106 pts | SL |
| 17:27 | **ninguna** | a 133 pts | ganador |
| 17:28 | **ninguna** | a 140 pts | ganador |
| 19:47 | **ninguna** | ninguna | ganador |
| 19:48 | presente, fill 7.2 pts por encima | ninguna | ganador |
| 22:52 | **presente ✓ + imán ✓** | ✓ | **SL** |

> El único fill que encajaba perfecto en la lógica de zonas fue **el perdedor**. Los ganadores no tenían zona viva.

Matiz importante: la secuencia #2 sí cerró **dentro** de la TP zone dibujada a mano (29181.39 / 29188.10). El imán como **objetivo** funcionó; lo que no funcionó fue la zona como **gatillo de entrada**.

### 5.3 El z separa ganadores de perdedores

| Fill | z_1m | z_3m | z_5m | Resultado |
|---|---:|---:|---:|---|
| 17:25 | +0.65 | **+1.26** | +0.29 | SL |
| 17:27 | −0.45 | **−1.03** | −0.21 | WIN |
| 17:28 | −0.07 | **−1.55** | −0.91 | WIN |
| 19:47 | +0.58 | +0.52 | +0.57 | WIN |
| 19:48 | −0.23 | +0.20 | +0.04 | WIN |
| 22:52 | **+1.69** | +0.63 | +0.38 | SL |

**Las dos pérdidas fueron las únicas con z claramente positivo** (USTEC ya estirado al alza respecto a SPY → comprar ahí llega tarde). Seis casos no son prueba estadística, pero es el mejor separador que salió de datos reales.

---

## 6. Niveles de SPY que USTEC no cubrió (medición auxiliar)

Proyectando high/low de SPY con β, anclado al cierre del mismo minuto:

| Faltante ≥ | n | por día | % llenado en 60 min | mediana min |
|---|---:|---:|---:|---:|
| 5 pts | 3,618 | 30.40 | 77.4% | 4 |
| 10 pts | 555 | 4.66 | 66.3% | 5 |
| 20 pts | 53 | 0.45 | 35.9% | 11 |

Pendiente: falta el control de azar (probabilidad de tocar un nivel a la misma distancia sin condición previa) para saber si el 66% supera al ruido.

---

## 7. Qué quedó funcionando en MT5

### 7.1 `GapsAndCrossLinesNotifier` — alertas

EA **solo visual**: no importa `CTrade`, no llama `OrderSend`. Adjunto a `USTEC,M1` y `SPY.NYSE,M1`.

| Input | Valor | Razón |
|---|---|---|
| `DiscrepancyBigPercent` | 40.0 | Cubre las velas marcadas (+39.5% a +46.1%) |
| `DiscrepancyLocalMaxBars` | 5 | Con 30 el filtro borraba las propias velas del usuario |
| `DiscrepancySmallPercent` | 50.0 | Lado contrario, ≈1.8/día |
| `MaxZoneAlertsPerHour` | 4 | Sin tope serían 72 avisos/día |
| `DivergenceZAlert` | −3.0 | La señal de la definición C |
| `CashSessionOnly` | true | Solo 16:30–23:00 servidor = 09:30–16:00 NY |
| `EnablePopupAlert` | false | Solo Telegram, sin popups |
| `PairedScreenshot` | true | Álbum USTEC + SPY en un mensaje |
| `AlertOnRelativeZones` | false | Definición A desactivada por falta de edge |

**Doble candado de sesión**: ventana horaria **y** `ReferenceIsActive()` (tick de SPY con menos de 120 s). El segundo es el que importa: hace la comprobación inmune al horario de verano. Si SPY no se mueve, no sale nada aunque el reloj diga que es hora.

**Validación de extremo a extremo (2026-08-26 19:09):**

```
GCL: PRUEBA divergencia 2026.08.26 22:38 dif=75.0% beta=52.6
     rango_real=9.2 rango_implicado=5.3
GCL: Telegram enviado con captura USTEC+SPY
```

Contraste MQL5 vs Python en esa misma vela:

| | beta | rango implícito | dif % |
|---|---:|---:|---:|
| Python | 52.58 | 5.26 | 75.0% |
| MQL5 | 52.6 | 5.3 | 75.0% |

Coinciden. Falta únicamente el disparo con una vela nueva en vivo.

### 7.2 `TradeNavigator` — navegador de operaciones (nuevo)

EA de **solo lectura**, compilado 0/0, desplegado en `MQL5\Experts\Advisors`.

| Función | Detalle |
|---|---|
| Agrupación | Deals del historial agrupados por `position_id`; precio de entrada y salida como media ponderada por volumen (soporta parciales) |
| Botones | `< TRADE` · `TRADE >` · `ULTIMO` |
| Dibujo | Flecha de entrada, flecha de salida, línea del recorrido, SL y TP si el deal los llevaba, etiqueta con puntos y P&L neto |
| Línea de info | posición n/total, ticket, dirección, volumen, hora, entrada → salida, puntos, **R** (si hay SL), P&L, duración |
| Contexto de divergencia | β, % de la vela y **z** del minuto exacto de la entrada |
| Panel resumen | trades, W/L, WR, PF y neto del periodo |

**Limitación de MT5: un solo EA por gráfico.** Adjuntarlo a `USTEC,M1` expulsaría al de alertas. Necesita su propia ventana (por ejemplo un segundo gráfico de USTEC).

---

## 8. Auditoría cerrada: 520 vs 521 GAPs

Venía pendiente del handoff anterior.

**Causa raíz**: el GAP #420 (2026-08-05 22:20, SHORT, `29653.0`–`29653.1`) mide exactamente 1 paso observado, y en doble precisión:

```
29653.1 − 29653.0 = 0.09999999999854481
```

El EA evaluaba `0.0999... < 0.10` → verdadero → descartaba un GAP legítimo. Python usaba el `trade_tick_size` real de MT5 (**0.01**, no 0.1) y no lo descartaba.

Corrección:

```mql5
double min_gap = MathMax(0, MinGapSteps) * TradePriceStep;
if(upper - lower < min_gap - 1e-6)
   return false;
```

Verificado: el EA vuelca `GCL_ea_gaps.csv` con **521 GAPs**, idéntico al backtest.

**Lección general**: toda comparación de precios contra un múltiplo de tick necesita epsilon.

---

## 9. Gotchas técnicos de MQL5 (los más caros de la sesión)

| # | Problema | Solución |
|---|---|---|
| 1 | El EA corre en **el hilo del gráfico**; `Sleep()` impide que MT5 procese `ChartNavigate` | Máquina de estados sobre `OnTimer`: encuadrar → ceder control → repintar → ceder control → capturar |
| 2 | `ChartRedraw()` solo **encola** el repintado | Capturar en el siguiente tick de timer, no en la misma llamada |
| 3 | `iBarShift` devuelve −1 si la serie no está sincronizada tan atrás | Respaldo con `Bars(symbol, tf, target, now) − 1` |
| 4 | MT5 **no recarga** el EA al copiar el `.ex5` | Re-adjuntar con `attach_ea_mt5.py` |
| 5 | `sendPhoto` y `sendMediaGroup` exigen multipart | Cuerpo armado byte a byte; foto emparejada coordinada entre instancias con `GlobalVariableTemp` |
| 6 | Automatizar la GUI de MT5 es peligroso | Activar gráficos con `WM_MDIACTIVATE`, **nunca con clic**, para no rozar el panel de 1-click trading. Adjuntar **SPY primero** |

---

## 10. Inventario de archivos

En `C:\Users\k_99_\Documents\Indicador ATAS\mt5_gaps_cross_lines`:

| Archivo | Función |
|---|---|
| `GapsAndCrossLinesNotifier.mq5` | EA de alertas (GAPs, divergencia, z, zonas) |
| `TradeNavigator.mq5` | **Nuevo.** Navegador visual del historial de trades |
| `attach_ea_mt5.py` | Adjunta EAs sin clic sobre el gráfico; SPY primero |
| `spy_leads_ustec.py` | Lead-lag, β global y mensual, niveles sin llenar |
| `divergence_signal.py` | Spread, z y movimiento posterior por tramo |
| `reverse_from_fills.py` | Reconstruye el contexto SPY/USTEC de cada fill real |
| `relative_discrepancy.py` | Detector de zonas relativas + simulación mensual |
| `discrepancy_scan.py` | Frecuencia de discrepancia por tamaño |
| `spy_discrepancy_setup.py` | Primer detector de niveles implicados |
| `audit_ea_vs_python_gaps.py` | Comparación de reglas de sesión NY vs broker |

Salidas: `outputs\spy_lead\`, `outputs\relative_b5\`, `outputs\spy_setup\`, `outputs\dst_2026\`.

---

## 11. Pendientes

| # | Pendiente | Detalle |
|---|---|---|
| 1 | Disparo en vivo | La alerta de divergencia nunca ha corrido con una vela nueva. Confirmar en la próxima apertura |
| 2 | Adjuntar `TradeNavigator` | Necesita gráfico propio; un EA por gráfico |
| 3 | Control de azar del relleno | El 66% de relleno de niveles ≥10 pts necesita baseline |
| 4 | Validación forward del z | Julio y agosto planos; hace falta confirmación en vivo |
| 5 | Costes | **Ningún número de este documento descuenta spread ni comisión** |
| 6 | Estudio de ticks | El adelanto de SPY, si existe, solo se ve con datos de tick |
| 7 | Encuadre de captura histórica | `ChartScreenShot` a veces sale con el borde derecho pese a que el gráfico está desplazado. No afecta a alertas en vivo |

---

## 12. Advertencias metodológicas

1. **Nada aquí incluye costes.** El spread de USTEC se come varios puntos por operación; con EV de +0.05R a +0.2R eso decide entre viable e inviable.
2. **Junio 2026 sesga todo.** Cualquier optimización sobre la muestra completa está mirando ese mes.
3. **Agosto, el mes más reciente, no confirma ninguna señal.**
4. **Las tres definiciones de discrepancia apuntan a direcciones distintas.** Confundirlas es el error más fácil: A no tiene edge, B es continuación, C es reversión.
5. **La regla mecanizada desde una descripción verbal falló; la ingeniería inversa desde fills reales fue productiva.** Repetir ese método.
6. **Los EAs nunca ejecutan órdenes.** Todas las operaciones del 2026-08-26 fueron manuales del usuario (magic = 0), confirmado por él.
