# Plan edge Codex — Handoff completo a Claude para LucidPro 150K

Fecha: 2026-07-26  
Autor del handoff: Codex  
Estado: **investigación detenida por orden del usuario; Claude debe continuar
sólo cuando el usuario se lo indique**.

## 1. Objetivo que no debe reinterpretarse

El usuario quiere encontrar un edge reproducible para operar NQ y pasar una
cuenta **LucidPro Evaluation de 150K** en un máximo de tres meses,
aproximadamente 63 sesiones:

- Profit target: `+$9,000`.
- Maximum Loss Limit EOD: `$4,500`.
- Daily Loss Limit: `$2,700`, tratado como límite operativo blando.
- Máximo oficial: `10` contratos minis.
- R:R bruto mínimo de cada entrada: `1:1`.
- Preferencia por entradas sniper y trailing, pero el trailing sólo debe
  conservarse si mejora o no degrada materialmente el edge.
- La estrategia debe ser sostenible; no basta con encontrar una muestra
  pequeña o un backtest sobreoptimizado.

Implementación utilizada para el floor Lucid:

```text
floor = min(peak_equity_EOD - 4500, +100)
```

El MLL se evalúa con el peak de equity al cierre del día y se bloquea en `+100`.
Fuentes oficiales consultadas:

- https://support.lucidtrading.com/en/articles/12890029-lucidpro-evaluation-account
- https://support.lucidtrading.com/en/articles/12890136-lucidpro-drawdown
- https://support.lucidtrading.com/en/articles/12890122-lucidpro-daily-loss-limit

Antes de simulación final, Claude debe volver a verificar que las reglas
oficiales no hayan cambiado.

## 2. Restricciones y autorizaciones del usuario

- Se autorizó descargar datos Databento para confirmación multiinstrumento.
- Límite indicado: no superar aproximadamente `80 GB` de nueva data.
- Mantener alrededor de `100 GB` como referencia práctica de disco; los
  scripts nuevos añaden además una reserva mínima automática de `25 GB`.
- Todo hallazgo importante debe documentarse en esta carpeta y enviarse por
  Telegram.
- No prometer que la cuenta se pasará: hay que demostrarlo con validación
  temporal y simulación de las reglas Lucid.
- R:R mínimo `1:1` es obligatorio.

## 3. Rutas importantes

Proyecto:

```text
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup
```

Código principal/Visual Logic:

```text
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup
```

Carpeta de handoffs y resultados Markdown:

```text
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_codex_claude
```

NQ RTH OHLCV-1s:

```text
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR\data\raw_dbn_2
```

ES RTH OHLCV-1s:

```text
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR\data\raw_dbn_es
```

Datos YM+RTY parciales:

```text
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\lucid150k_multi_data\combined_early
```

Datos overnight NQ+ES para V14:

```text
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\lucid150k_sniper_v14_overnight
```

Resultados persistentes/Telegram:

```text
C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score
```

## 4. Trabajo previo de Liquidity Burst y Visual Logic

El archivo `02_Visual_Logic.cs` ya fue modificado y el proyecto compiló
correctamente. El label existente quedó:

```text
BUY burst  -> BURST 52% SELL PROBABILITY
SELL burst -> BURST 53% BUY PROBABILITY
```

Las probabilidades proceden de los conteos observados:

- BUY burst: `44/85` terminaron en SELL.
- SELL burst: `52/99` terminaron en BUY.

No deben presentarse como probabilidades universales ni como edge confirmado;
son tasas empíricas del bloque estudiado.

Hallazgos de Liquidity Burst:

- El score LB V2 fue estable como descriptor, pero no tuvo endpoint direccional:
  `rho=-0.163` y el intervalo incluyó cero.
- El bloque de 29 eventos de 2024 para V2 permanece **sellado**. No abrirlo ni
  usarlo para formular o ajustar hipótesis.
- El protocolo del usuario
  `C:\Users\k_99_\Desktop\Protocolo_Separacion_Breakout_vs_Absorcion_Liquidity_Burst.md`
  es un buen charter, pero exige convertir etiquetas a umbrales numéricos,
  separar mecanismo de outcome, controlar multiplicidad y preregistrar cada
  comparación.
- El experimento V5 de mecanismo LB pareció prometedor en una muestra muy
  pequeña, pero V7 mostró que era un artefacto de selección estructural.

## 5. Errores metodológicos ya encontrados y corregidos

### DST

Varios scripts antiguos trataban `13:30 UTC` como cash open durante todo el año.
Eso omite el invierno y producía un falso sesgo long. Toda investigación nueva
usa `America/New_York` y convierte después a UTC.

### Simulación Lucid

Una simulación antigua mantenía el MLL como `peak - 4500` para siempre y añadía
un timeout de 120 días. Eso no representa correctamente el floor que se bloquea
en `+100`, ni el objetivo del usuario de 63 sesiones. No reutilizar esa lógica.

### Data RTH

Los archivos NQ y ES existentes empiezan a las 09:30 NY y terminan alrededor de
15:59. No contienen overnight/premarket. Nunca inferir gap o inventario
overnight desde esos archivos.

### Gestión de trades

El simulador común:

- Usa coste total conservador de `4 ticks NQ`.
- Evalúa stop antes que target cuando ambos podrían tocarse dentro de la misma
  barra de 1 segundo.
- En la gestión principal usa target `2R`, activa break-even neto y trailing
  `1R` al alcanzar `+1R`.
- Mantiene un diagnóstico separado con stop/target fijo `1:1`.

Con frecuencia el trailing redujo EV. No debe imponerse por preferencia si no
supera el diagnóstico fijo en validación temporal.

## 6. Hipótesis probadas y resultados

Cada versión se preregistró y se hasheó antes de calcular outcomes. Ninguna
autorizó abrir/descargar el holdout verdadero `2020-01-01..2022-04-22`.

| Versión | Hipótesis | DEV principal | Conclusión |
|---|---|---:|---|
| V1 | ES lidera breakout NQ / divergencia y reclaim | S1 `n=73`, EV `-0.0037R`, PF `0.993`; S2 `n=86`, EV `-0.0861R`, PF `0.853` | Falla |
| V2 | Acceptance/retest y failed reclaim | `n=95`, EV `-0.0494R`; segunda `n=129`, EV `-0.1258R` | Falla |
| V3 | Primer ORB long con DST correcto | `n=497`, EV `+0.0058R`, PF `1.011`, `2/5` años | El viejo sesgo UP desaparece |
| V4 | Breakout NQ confirmado por ES/YM/RTY | `n=64`, EV `-0.0238R`, PF `0.955`, `1/2` años | Falla |
| V5 | LB acceptance vs absorption | Continuation `n=16`, EV `+0.3047R`, PF `1.918`; frecuencia insuficiente | Promesa no reproducible |
| V6 | Gap >=25% del rango previo y sostenido en OR | `n=94`, EV `-0.0051R`, PF `0.990` | Falla |
| V7 | LB acceptance con 20/40 ticks | `n=54`, EV `+0.0630R`, PF `1.135`; 2022 positivo, 2023 negativo | Refuta la selección de V5 |
| V8 | NQ rompe mientras ES/YM/RTY están neutrales | `n=248`, EV `-0.0964R`, PF `0.817` | Falla |
| V9 | Conflicto multiinstrumento y fade | `n=11`, EV `-0.401R`, PF `0.475` | Falla y muy poca muestra |
| V10 | OR5, tres cierres, ES confirma, pullback | `n=109`, EV `-0.1193R`, PF `0.785` | Falla |
| V11 | Continuación del IB30 aceptada | `n=380`, EV `-0.0738R`, PF `0.860`; stress `-0.175R` | Falla |
| V12 | Ruptura IB30 aceptada, reclaim <=300 s y fade | `n=284`, EV `-0.1941R`, PF `0.677`; `0/2` años | Falla |
| V13 | Opening drive eficiente + pullback + reanudación | `n=34`, EV `-0.2493R`, PF `0.572`; `0/2` años | Falla |

Lectura agregada:

1. La continuación pierde desde OR1 hasta IB30.
2. Invertir automáticamente el breakout del IB30 también pierde.
3. Añadir confirmación simple de ES o breadth no convierte el nivel en edge.
4. La eficiencia visual del opening drive tampoco basta.
5. El trailing no rescató ninguna familia y en V13 restó `-0.0904R`.
6. Todavía **no existe un edge aprobado** para la cuenta 150K.

Documentos de detalle:

```text
20260726_047_LUCID150K_SNIPER_V1_DEV_FAIL.md
20260726_048_LUCID150K_SNIPER_V2_DEV_FAIL.md
20260726_049_LUCID150K_SNIPER_V3_DST_REMOVES_UP_EDGE.md
20260726_050_LUCID150K_V4_BREADTH_DEV_FAIL.md
20260726_051_LUCID150K_V5_LB_MECHANISM_FAIL.md
20260726_052_LUCID150K_V6_GAP_FAIL.md
20260726_053_LUCID150K_V7_LB_SNIPER_FAIL.md
20260726_054_LUCID150K_V8_NQ_LEADS_FAIL.md
20260726_055_LUCID150K_V9_CONFLICT_FADE_FAIL.md
20260726_056_LUCID150K_V10_OR5_FAIL.md
20260726_057_LUCID150K_V11_IB30_FAIL.md
20260726_058_LUCID150K_V12_IB_FAILURE_FAIL.md
20260726_059_LUCID150K_V13_OPENING_DRIVE_FAIL.md
```

## 7. Estado exacto de V14: no se ha ejecutado

Carpeta:

```text
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\lucid150k_sniper_v14_overnight
```

Hipótesis congelada: corrección de inventario overnight NQ+ES.

Regla resumida:

1. Medir la fracción de cierres Globex de un minuto por encima del último close
   RTH previo.
2. Exigir inventario concentrado y concordante entre NQ y ES.
3. Exigir que la vela cash 09:30–09:35 se mueva contra el inventario y hacia el
   ancla.
4. Entrar contra el inventario después de 09:35.
5. Stop estructural `+4 ticks`, riesgo entre 20 y 80 ticks, target 2R y trailing
   desde 1R.

Archivos:

```text
PREREGISTRO_LUCID150K_SNIPER_V14.md
PREREG_HASH.sha256
run_v14.py
nq_es_1m_20220424_20260630.dbn.zst
```

Integridad:

- Prerregistro:
  `7648EA736B5369A738A2CFE921C932BE7896D7F54CBE224F2DCCFF5AD1A23613`
- `run_v14.py`:
  `D7675EFA5853369769257C5C23B05BEB031BF93BBCB7B0A92D6AE35FA5631D0E`
- Data bulk:
  `B32BA5D527DF4D4857636F523431BAE1241D7D2C1E52D2173F4DF6F3CEA1FF2F`
- Tamaño bulk: `50,267,822 bytes`, aproximadamente `47.94 MiB`.

Costes cotizados:

- Descarga por ventanas exactas: `US$6.9769` esperado,
  `US$8.7211` con margen 25%.
- Para evitar aproximadamente una hora de llamadas por sesión se descargó un
  bloque continuo cotizado en `US$10.7276`.
- Antes del bloque se completaron 16 ventanas individuales, `546,837 bytes`;
  coste aproximado adicional `US$0.11`.
- Total esperado de adquisición: aproximadamente `US$10.84`; verificar en la
  cuenta Databento si se necesita el importe facturado exacto.

Databento emitió advertencia de calidad reducida en:

```text
2025-09-17
2025-09-24
2025-11-28
```

`run_v14.py` ya contiene `DEGRADED_DATES` para excluirlas.

### Advertencia crítica antes de correr V14

El script actual aún no fue ejecutado, pero materializa trades de 2022–2026 en
`ALL_TRADES.csv` antes de decidir si DEV pasa. Aunque sólo publica métricas 2024
si DEV pasa, esto viola la separación estricta porque los outcomes pseudo ya
quedarían calculados.

Claude debe corregir **antes del primer run**:

1. Crear una etapa que procese únicamente DEV `2022-04-25..2023-12-31`.
2. Congelar y hashear el source de esa etapa.
3. Ejecutar DEV.
4. Sólo si todos los gates DEV pasan, crear/ejecutar una etapa separada para
   2024.
5. El stress 2025–2026 puede mantenerse descriptivo, pero es preferible
   calcularlo después de la decisión DEV para evitar decisiones post hoc.
6. No modificar los umbrales de la hipótesis V14 después de ver DEV. Si existe
   un bug semántico, corregirlo bajo nombre `V14b`, explicar el bug, crear nuevo
   prerregistro y nuevo hash.

El bulk empieza el `2022-04-24`; no contiene el holdout verdadero anterior al
`2022-04-22`.

## 8. Instrucciones concretas para que Claude continúe

### Paso A — Auditoría reproducible de V14

1. Verificar que no exista ningún proceso de investigación activo.
2. Validar SHA-256 de prerregistro, source y data contra este documento.
3. Abrir sólo metadata y una muestra mínima del DBN para verificar:
   `ohlcv-1m`, símbolos `NQ.c.0` y `ES.c.0`, timestamps UTC y cobertura.
4. Separar DEV/pseudo como se indicó arriba.
5. Compilar con `python -m py_compile`.
6. Ejecutar únicamente DEV.
7. Guardar `RESULT.json`, `ALL_TRADES_DEV.csv`, errores, dispositions y hashes.
8. Documentar el resultado en el siguiente Markdown numerado.
9. Enviar el hallazgo a Telegram con `persistent=True`.

### Paso B — Gates V14 ya congelados

DEV debe cumplir simultáneamente:

- `n >= 50`.
- Frecuencia `>=2.0 trades/mes`.
- EV neta `>+0.12R`.
- PF `>1.35`.
- `2/2` años positivos.
- `>=75%` de mitades positivas.
- EV trailing menos EV fija 1:1 `>=-0.05R`.

Pseudo 2024, únicamente después de DEV:

- `n>=25`.
- EV `>0`.
- PF `>1.15`.
- Límite inferior bootstrap 95% de EV `>-0.08R`.

Si falla cualquier gate: no abrir holdout y no optimizar los thresholds de V14.

### Paso C — Si V14 falla

No crear V15 como una variación cosmética de 0.75/0.65, 5 minutos o 40 ticks.
El siguiente test debe aportar información independiente.

Orden recomendado:

1. **V15 walk-forward premarket/cash response.** Definir antes del outcome un
   conjunto pequeño de features causales: inventario NQ, inventario ES,
   overnight return normalizado, close location, volumen relativo y respuesta
   cash. Entrenar sólo en 2022 y evaluar de forma totalmente temporal en 2023.
   Usar regularización fuerte y un único threshold fijado en train. No usar
   2024 para selección.
2. **V16 MBO/Liquidity Burst causal.** Volver al mecanismo sólo si hay datos MBO
   suficientes fuera del bloque sellado. Separar aceptación, absorción y
   agotamiento con labels numéricos; máximo una familia preregistrada, sin
   barrer decenas de umbrales.
3. **V17 confirmación multiinstrumento de régimen, no de nivel.** YM/RTY deben
   usarse para medir risk-on/risk-off o dispersión, no simplemente “dos de tres
   rompen”. Cotizar y descargar sólo las sesiones faltantes después de un
   prerregistro y manteniendo el cap de 80 GB.
4. Si ninguna familia supera validación temporal, concluir honestamente que los
   datos actuales no demuestran un edge. No rebajar gates para fabricar uno.

### Paso D — Holdout verdadero

Sólo después de pasar DEV y 2024:

1. Cotizar NQ/ES y cualquier instrumento requerido para
   `2020-01-01..2022-04-22`.
2. Mostrar coste y tamaño antes de descargar.
3. Descargar una sola vez.
4. Congelar código, configuración, hashes y seed antes de abrir outcomes.
5. Un único test confirmatorio. Si falla, la estrategia queda rechazada; no
   ajustar y volver a probar sobre ese holdout.

### Paso E — Simulación de la cuenta Lucid 150K

Un backtest positivo todavía no satisface el objetivo. Para la estrategia que
pase holdout:

1. Convertir ticks/R a dólares con valor NQ, comisiones y slippage conservador.
2. Evaluar tamaños enteros sin exceder 10 minis.
3. Aplicar DLL `$2,700`, MLL EOD `$4,500`, lock del floor en `+100` y target
   `+$9,000`.
4. Detener trading diario antes del DLL con buffer operativo.
5. Ejecutar block bootstrap por días, preservando rachas y días sin señal.
6. Medir probabilidad de alcanzar `+$9,000` antes de 63 sesiones, probabilidad
   de breach, drawdown, peor racha, días medianos y percentiles.
7. Hacer stress de costes, un tick adicional de slippage, trades perdidos,
   latencia y reducción de fill.
8. Seleccionar sizing por robustez, no por la mayor curva histórica.
9. Preregistrar el umbral mínimo de probabilidad de pase antes de simular. Una
   propuesta razonable es exigir probabilidad bootstrap `>=70%` dentro de 63
   sesiones y probabilidad de breach `<=10%`, además de estabilidad por
   subperiodos; Claude debe documentar y congelar la decisión antes del cálculo.

Con stop de 40 ticks, un NQ arriesga aproximadamente `$200` antes de costes.
Dos o tres NQ serían `$400–$600` de riesgo base; no asumir que 10 contratos son
operables sólo porque el límite oficial los permite.

## 9. Telegram

Módulo:

```python
from telegram_run_summary_after_sync import send_text
```

Patrón:

```python
send_text(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score",
    "mensaje",
    persistent=True,
)
```

No imprimir ni copiar el token. La API key Databento está en:

```text
C:\Users\k_99_\Desktop\codding\data_footprint_generator\databento_api_key.txt
```

Tampoco debe exponerse. Las notificaciones persistentes de V1–V13 se enviaron
correctamente; V14 no tiene outcome y no se envió como hallazgo.

## 10. Estado al entregar

- Procesos de investigación activos: `0`.
- V14 preregistrada: sí.
- Data V14 descargada: sí.
- V14 ejecutada: **no**.
- Pseudo 2024 de V14 abierto: **no**.
- Holdout 2020–2022 descargado/abierto: **no**.
- Edge aprobado: **no**.
- Próxima acción autorizada en este momento: ninguna; esperar que el usuario
  indique a Claude continuar.

`INFORMATION_STATUS=HANDOFF_COMPLETE_LUCID150K_TO_CLAUDE`
