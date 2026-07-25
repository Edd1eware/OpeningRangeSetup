# PREREGISTRO ADAPTADO — Nuevo enfoque A/B ORB NQ

Estado: **DISEÑO CONGELADO ANTES DEL GATE CERO DE ACCIONABILIDAD**  
Fecha: 2026-07-24  
Fuentes conceptuales:

- `C:\Users\k_99_\Desktop\fmd_files\RUNBOOK_AB_ORB_NQ.md`
- `C:\Users\k_99_\Desktop\fmd_files\PREREGISTRO_AB_ORB_NQ.md`

Este documento adopta las defensas contra sobreajuste de esos archivos, pero
corrige los puntos que no son compatibles con la investigación ya realizada.
Los resultados anteriores de MATRIX y MBO son conocidos; por tanto, esto es un
**plan de análisis registrado para una revisión**, no un preregistro prospectivo
de toda la investigación.

## 1. Corrección decisiva al Test Cero original

Las etiquetas actuales no son independientes del resultado:

- A se asigna cuando `Result_Label=TP`, `MAE<=20` y `MFE>=TP inicial`;
- B se asigna cuando `Result_Label=SL`, `MFE<=20` y `MAE>=SL inicial`;
- C contiene las trayectorias restantes.

Por ello, probar que A y B difieren en MFE, MAE, TP, SL o PnL sería circular.
Ese Test Cero queda **prohibido** y no puede justificar continuar.

La etiqueta se interpreta honestamente como:

- A: reversión limpia favorable después del burst;
- B: continuación limpia del burst, adversa para la entrada de reversión;
- C: trayectoria variable.

No se afirmará que A/B sea una verdad microestructural observada directamente.

## 2. Gate Cero adaptado: accionabilidad temprana

### Pregunta

¿Las familias terminales A y B ya muestran una separación de precio útil durante
el primer segundo **posterior a `t_decision`**?

Si no existe una divergencia temprana defendible, no se construirá otro
clasificador MBO: el objetivo aparece demasiado tarde para la entrada.

### Datos

- Universo disponible: las 100 sesiones discovery de 2022–2024 ya observadas.
- Muestra limpia: A=29 y B=41; C=30 se reporta pero no entra al contraste.
- Una sesión equivale actualmente a un evento; el remuestreo sigue usando la
  fecha como bloque para conservar la regla si aparecen varios eventos por día.
- Fuente del outcome temprano: `observational/burst_response_events.csv`.
- Se usa exclusivamente `Response_Horizon_Seconds=1`.
- La respuesta post-decisión nunca será predictor.
- 2025–2026 permanece cerrado.

### Endpoint primario único

```text
Y = Directional_Displacement_Ticks
efecto = media(B) - media(A)
```

`Directional_Displacement_Ticks` está orientado en la dirección del burst. Se
espera B>A: continuación positiva para B y reversión o menor avance para A.

Para la reparación uniforme con tape Databento:

```text
p0 = último trade con ts_event < t_decision dentro de los 100 ms previos
p1 = último trade con ts_event < t_decision + 1 segundo
Y  = signo_burst * (p1 - p0) / 0.25
```

Se exige al menos un trade antes y otro desde `t_decision` hasta el fin
exclusivo. No se redondean timestamps. Si falta cualquiera, el Gate Cero vuelve
a `INTEGRIDAD FAIL`.

### Incertidumbre

- 10,000 bootstrap por bloques de fecha.
- IC95% percentil.
- 10,000 permutaciones de A/B dentro de año y BUY/SELL.
- Semilla: 20260724.
- MDE preregistrado: 2 ticks de diferencia B−A.
- Umbral mínimo de utilidad: 1 tick.
- Alfa bilateral: 0.05.
- Potencia objetivo: 0.80.

### Regla del Gate Cero

| Resultado | Criterio | Acción |
|---|---|---|
| PASS | efecto en dirección correcta, límite inferior IC95% > +1 tick y p<=0.05 | pasar a ingeniería MBO |
| NO CONCLUYENTE | IC95% cruza 0 y potencia para MDE=2 ticks <0.80 | no declarar fallo; dimensionar muestra no selectiva |
| REFUTACIÓN | IC95% cruza 0 y potencia >=0.80, o IC completo está en dirección contraria | detener esta taxonomía para entrada temprana |
| SEÑAL SUBUMBRAL | IC95% no cruza 0, pero no cumple simultáneamente utilidad >1 tick y p<=0.05 | no avanzar a MBO; confirmar primero con muestra no selectiva |
| INTEGRIDAD FAIL | faltan respuestas, duplicados, reloj incoherente o respuesta no posterior a `t_decision` | corregir datos; no interpretar |

`Response_MFE_Ticks`, `Response_MAE_Ticks`, dwell, reclaim y demás columnas son
diagnósticos secundarios; no pueden cambiar el veredicto.

## 3. Qué se conserva del runbook FMD

Si Gate Cero da PASS:

1. **Warm-up empírico.** El snapshot da estado, no historia. Cada feature con
   edad, duración o tasa previa debe converger al variar el inicio del historial.
2. **Nulo calibrado.** Los pseudo-eventos se muestrearán en el mismo régimen de
   apertura, 08:30–09:30 America/Chicago, estratificados por minuto desde la
   apertura y excluyendo ±60 segundos de bursts reales.
3. **Sensibilidad.** Los umbrales del detector se perturban ±15% y ±30%. Si el
   conjunto de eventos cae por debajo de Jaccard 0.70 con una perturbación de
   ±15%, el diseño falla antes de entrenar.
4. **Reconciliación externa.** El replay MBO derivado se comparará con MBP-10 y
   OHLCV-1s nativos. La reconciliación interna contra el mismo replay no basta.
   Cualquier descarga adicional requiere autorización previa.
5. **Purga, embargo y bloques diarios.** Nunca CV aleatorio plano.
6. **Nulo por permutación, IC95% y corrección Holm** para diagnósticos
   secundarios.
7. **Una sola revisión.** Cualquier cambio posterior se registra como post hoc.

### Regla de duplicados del exportador

Una repetición completamente idéntica en todas las columnas exportadas se
colapsa a una fila y se contabiliza. Dos filas del mismo `BurstId` y horizonte
que difieran en cualquier campo constituyen `INTEGRIDAD FAIL`.

## 4. Correcciones adicionales al runbook FMD

- Las 100 sesiones actuales fueron seleccionadas por familia; no son un censo.
  Sirven para ingeniería y discovery, no para prevalencia, calibración final ni
  confirmación prospectiva.
- Con A=29 y B=41 no se interpretará un IC amplio como refutación automática.
- No se definirá A/B con las mismas variables MBO que después intenten
  separarlas; eso sería tautológico.
- Los pseudo-eventos no se tomarán de toda la jornada porque mezclarían el
  régimen de apertura con horas de menor actividad.
- El precio ATAS puede servir como control informativo, pero libro, tape y cola
  deben reconstruirse internamente desde una fuente sincronizada.
- Las dos sesiones de rollover 2022-06-13 y 2023-06-13 se excluyen de cualquier
  conclusión MBO hasta resolver NQM/NQU. No afectan el Gate Cero, que no usa MBO.

## 5. Fases posteriores, todavía no autorizadas por Gate Cero

### Fase 1 — Ingeniería sobre las seis sesiones técnicas

- Perfilar warm-up por feature.
- Calibrar nulos por pseudo-eventos.
- Auditar sensibilidad del detector.
- Cotizar, y sólo con autorización descargar, MBP-10/OHLCV-1s para
  reconciliación externa.

### Fase 2 — Congelar representación

La lista final de predictores no se fijará hasta que la ingeniería sin etiquetas
termine. No se buscarán predictores observando A/B. La representación debe
conservar orden temporal, identidad de orden y tiempo entre eventos.

### Fase 3 — Discovery

- Las 100 sesiones actuales sólo se usan como discovery conocido.
- LOYO 2022/2023/2024, estabilidad BUY/SELL, bootstrap diario y permutación.
- Se compara contra `MATRIX_TRANSITIONS`.
- CatBoost no reemplaza al modelo primario regularizado.

### Fase 4 — Confirmación

2025–2026 se abre una sola vez únicamente si todas las puertas previas pasan.
No se descargarán nuevas fechas por cercanía a un umbral.

## 6. Reglas de paro

Se detiene la línea si:

1. Gate Cero produce refutación con potencia suficiente.
2. La reconciliación externa falla.
3. La selección de eventos colapsa ante perturbaciones pequeñas.
4. Se detecta contaminación de outcome en predictores.
5. Se agota la única revisión permitida.

## 7. Registro de desviaciones

| Fecha | Cambio | Motivo | Outcome observado |
|---|---|---|---|
| 2026-07-24 | Se explicitó el colapso de duplicados exactamente idénticos | El control previo detectó dos copias idénticas de `LB_20220608_093102_SELL_0001`; no se había calculado ninguna métrica A/B | No |
| 2026-07-24 | Se operacionalizó el endpoint uniforme como último trade antes de decisión contra último trade antes de decisión+1 s | Reparar las 14 respuestas ausentes con una sola fuente y una regla reproducible | No |
