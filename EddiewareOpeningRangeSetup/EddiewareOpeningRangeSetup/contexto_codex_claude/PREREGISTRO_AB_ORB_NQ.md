# PREREGISTRO — Separación A/B en ORB NQ

**Estado:** BORRADOR (no congelado)
**Autor:** Eduardo
**Fecha de congelación:** \_\_\_\_\_\_\_\_
**Git commit:** \_\_\_\_\_\_\_\_
**SHA256 de este archivo:** \_\_\_\_\_\_\_\_

> Este documento solo tiene valor si se congela **antes** de mirar cualquier resultado.
> Congelar = commit + tag + hash publicado. Sin hash previo, no es preregistro; es narrativa.

---

## 0. Qué queda congelado

| Elemento | Congelado | Notas |
|---|---|---|
| Definición de etiqueta A/B | SÍ | §4 |
| Las 8 features MBO | SÍ | §5 |
| Umbrales de la regla (3:1, 70, 3 niveles, 20 ticks) | SÍ | §5.2 |
| Endpoint primario | SÍ, uno solo | §2 |
| Umbrales de decisión | SÍ | §7 |
| Protocolo de validación | SÍ | §6 |
| Test set bloqueado | SÍ | §6.4 |
| Hiperparámetros CatBoost | NO | libres dentro del CV purgado, nunca tocando test |

Cualquier cambio a una fila "SÍ" después del congelamiento se registra en §11 y **consume presupuesto de iteración** (§9).

---

## 1. Hipótesis

**H_0 (taxonomía).** La distribución de resultado condicional es idéntica entre eventos A y B.
**H_1 (taxonomía).** Difieren.

**H_0 (features).** Las 8 features MBO no separan absorción de breakout limpio por encima del nulo calibrado.
**H_1 (features).** Sí lo hacen.

**Orden obligatorio:** si no se rechaza H_0(taxonomía), el programa termina. No se construye clasificador. Distinguir perfectamente dos clases con el mismo resultado esperado vale cero.

---

## 2. Endpoint primario (UNO)

```
Endpoint = ____________________________________________
Métrica  = ____________________________________________
Dirección esperada = _________________________________
```

Sugerencia: diferencia en `E[MFE/ORTicks]` entre clases mecánicas (absorción vs limpio), o AUC out-of-sample sobre el test bloqueado.

Todo lo demás es **exploratorio** y se rotula así en cualquier reporte, sin excepción.

---

## 3. Universo y muestreo

- Periodo: \_\_\_\_\_\_\_\_ a \_\_\_\_\_\_\_\_
- Criterio de inclusión: **censo**, no muestra seleccionada. Toda sesión que cumpla el filtro entra.
- Filtro de exclusión (fijar ahora, mecánico): \_\_\_\_\_\_\_\_
- Unidad de observación: **evento = ataque al borde de la OR** (no sesión). Primer test, retest y falla-reintento son eventos distintos.
- n esperado: \_\_\_\_\_\_\_\_ eventos / \_\_\_\_\_\_\_\_ sesiones

**Potencia.** Para AUC=0.60 vs 0.50, α=.05 bilateral, potencia .80: orden de **250–300 por clase**. Recalcular con el bootstrap exacto de §6.3 antes de congelar. Si el n proyectado no alcanza, se ajusta el universo **ahora**, no después.

---

## 4. Etiqueta mecánica (sin contaminación de resultado)

Definición puramente de libro. **Prohibido** que MFE, MAE, TP, SL, PnL o cualquier evento posterior a `t_decision` entren aquí.

**Absorción:**
```
agresión acumulada en L0 ≥ ____
Y  BBO no avanza durante Δt = ____
Y  add_flow(L0) > cancel_flow(L0)   [la cola se repone]
```

**Breakout limpio:**
```
BBO avanza ≥ ____ ticks
Y  cancel_flow domina sobre fills en el nivel abandonado
```

**No clasificable:** todo lo demás. Se reporta su fracción; no se fuerza a ninguna clase.

> Verificar que las features separan estas clases es **casi tautológico** si las features definen la etiqueta. Ese resultado no cuenta como evidencia y no se reporta como tal.

---

## 5. Features congeladas

### 5.1 Lista

| # | Feature | Warm-up requerido | Censura izq. |
|---|---|---|---|
| 1 |  |  |  |
| 2 |  |  |  |
| 3 |  |  |  |
| 4 |  |  |  |
| 5 |  |  |  |
| 6 |  |  |  |
| 7 |  |  |  |
| 8 |  |  |  |

El snapshot da **estado**, no **historia**. Toda feature con componente de duración (edad de orden, tasa de cancelación previa, refills acumulados) está censurada por izquierda aunque el libro esté completo. El warm-up se mide empíricamente, no se asume.

### 5.2 Umbrales de la regla

`ratio_imbalance = 3:1` · `vol_min_celda = 70` · `niveles_apilados = 3` · `distancia_borde = 20 ticks`

Sensibilidad ±30% documentada en: \_\_\_\_\_\_\_\_
Si alguna feature colapsa ante perturbación pequeña, el sobreajuste ya ocurrió en la especificación y se declara aquí antes de continuar.

---

## 6. Validación

### 6.1 Purga y embargo
CV purgado con embargo de \_\_\_\_ sesiones. Nunca CV plano.

### 6.2 Clustering
Errores clusterizados por día. Los eventos intra-sesión no son independientes.

### 6.3 Incertidumbre
Block bootstrap por día, \_\_\_\_ réplicas. Todo estimador se reporta con IC95%.

### 6.4 Test bloqueado
- Definido el: \_\_\_\_\_\_\_\_
- Rango: \_\_\_\_\_\_\_\_
- Hash del split: \_\_\_\_\_\_\_\_
- Aperturas permitidas: **1**

### 6.5 Nulo calibrado
Distribución nula por feature vía pseudo-eventos (timestamps aleatorios, niveles no-OR). Sin esto no se sabe si un valor extremo en `t_burst` es extremo o es lo que hace el libro de NQ todo el día.

### 6.6 Multiplicidad
Corrección: \_\_\_\_\_\_\_\_ (Bonferroni / Holm / BH). Fijar ahora.

---

## 7. Regla de decisión — umbrales fijados ANTES de ver datos

| Resultado | Criterio | Acción |
|---|---|---|
| **Éxito** | IC95% inferior del endpoint > \_\_\_\_ | Pasa a dimensionamiento |
| **No concluyente** | IC95% cruza el nulo Y potencia < .80 | Ampliar n. No cuenta como fallo |
| **Refutación** | IC95% cruza el nulo CON potencia ≥ .80 | Alto |

Escribir los números. Un umbral en blanco al momento de congelar equivale a no tener umbral.

---

## 8. Bug vs. refutación

| Categoría | Diagnóstico | Costo |
|---|---|---|
| **Bug** | contrato mal resuelto, look-ahead, error de replay | Gratis. Corregir y recorrer |
| **Feature censurada** | warm-up insuficiente demostrado en §5.1 | Gratis. Corregir y recorrer |
| **Potencia insuficiente** | IC amplio, potencia < .80 | Gratis. Ampliar n |
| **Features no capturan mecanismo** | features fallan vs nulo calibrado | 1 revisión preregistrada, datos nuevos |
| **Clases no difieren** | H_0(taxonomía) no rechazada con potencia | **Alto. No negociable** |

La clasificación se hace **contra esta tabla**, no contra la intuición del momento. Si un resultado no encaja limpiamente en una fila, es refutación.

---

## 9. Presupuesto de iteración

- Revisiones permitidas tras congelar: **1**
- Cada revisión: preregistro nuevo + datos nuevos + test bloqueado nuevo
- Agotado el presupuesto: alto, independientemente de qué tan cerca parezca estar

Todo grado de libertad ejercido después de ver datos se anota en §11. El ledger es la única defensa contra el sobreajuste lento, que desde adentro se siente exactamente como "casi lo tengo".

---

## 10. Reglas de paro

Alto inmediato si:
1. H_0(taxonomía) no se rechaza con potencia ≥ .80
2. Se agota el presupuesto de §9
3. Se detecta contaminación de outcome en §4
4. La reconciliación externa (MBP-10 derivado vs. Databento; trades agregados a OHLCV-1s) falla

---

## 11. Registro de desviaciones (append-only)

| Fecha | Sección | Cambio | Motivo | ¿Post-hoc? | Costo |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

Nunca se edita ni se borra una fila. Una desviación no registrada invalida el preregistro completo.

---

## Anexo — Orden de ejecución

1. **Gratis, hoy, sin MBO:** Test Cero — ¿A y B difieren en resultado? Etiquetas ATAS + MFE/MAE del histórico completo. Puede matar el programa antes de gastar un peso
2. **Gratis, 6 sesiones:** perfilado de warm-up · nulo calibrado · sensibilidad de umbrales · reconciliación externa
3. **Congelar este documento.** Hash + commit + tag
4. **Comprar censo** (~USD 180–220), muestreo no selectivo
5. **Correr.** Una vez
