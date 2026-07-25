# HANDOFF DE INVESTIGACIÓN — LIQUIDITY BURST / MBO V2

**Fecha de corte:** 2026-07-25  
**Objetivo único del proyecto:** detectar un `Liquidity Burst` y, usando exclusivamente información causal disponible antes de `t_decision`, distinguir una **ABSORCIÓN LIMPIA** de un **BREAKOUT LIMPIO** sin lookahead, sin overfit y sin destruir la frecuencia operativa.

> **Leer primero:** el camino perceptual A/B/C quedó cerrado. El siguiente paso no es volver a etiquetar imágenes ni descargar más datos. Es construir y congelar un **score mecánico continuo defensa–aceptación** a partir de la secuencia MBO ya disponible, demostrar primero su estabilidad sin outcomes y abrir discovery una sola vez únicamente si pasa esa puerta.

---

## 1. Veredicto actual

**Todavía NO somos capaces de afirmar que separamos de forma estable una absorción limpia de un breakout limpio.**

La representación visual categórica logró una señal direccional interesante:

- Claude y Codex coincidieron originalmente en `82/98 = 83.67%`.
- Cuando ambos emitieron una dirección A/B, coincidieron en `62/62`.
- En dos perturbaciones cosméticas independientes hubo **cero inversiones A↔B**.

Sin embargo, la frontera entre una clasificación direccional y la abstención `C` no fue reproducible:

- AMD-2: `9/62 = 14.52%` de cambios, por encima del máximo congelado de `10%`.
- AMD-3: `7/53 = 13.21%` de cambios, también por encima de `10%`.
- Todos los fallos fueron `A/B → C`; nunca `A → B` ni `B → A`.

Esto es **evidencia de consistencia direccional condicionada a clasificar**, pero no evidencia predictiva. El mapping y los outcomes nunca se abrieron.

---

## 2. Reglas de gobierno que deben conservarse

1. **Claude Fable y Codex deben dialogar y converger antes de cualquier decisión importante de diseño.**
2. Guardar el contexto y las decisiones conjuntas en:

   `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_codex_claude`

3. Documentar cualquier hallazgo que acerque al objetivo y enviarlo también por Telegram.
4. La etiqueta humana de Eduardo queda excluida del clasificador operativo por decisión expresa del usuario; se conserva solamente como auditoría.
5. No imponer esperas artificiales, prohibiciones de abrir carpetas ni “N días de ceguera”. La causalidad se protege mediante:

   - cutoff temporal explícito;
   - paquetes completos `F_LAST`;
   - exclusión de eventos posteriores;
   - fórmulas y gates congelados;
   - hashes;
   - split temporal sellado;
   - una sola apertura de cada conjunto de outcomes.

6. No usar `MFE`, `MAE`, `TP`, `SL`, `PnL` ni el resultado futuro para construir, normalizar, seleccionar o ponderar predictores.
7. Al terminar cada etapa relevante, enviar a Telegram:

   - resultado;
   - integridad causal;
   - veredicto;
   - qué falta;
   - próximos pasos.

---

## 3. Datos existentes y qué ya se comprobó

### 3.1 Primer dataset MBO agregado, sin snapshot inicial

- 100 sesiones discovery.
- `620,988` identificadores de orden.
- `21.88%` de censura izquierda.
- Snapshot inicial: `0`.
- Se excluyeron `595` eventos posteriores al cutoff nominal.
- Join MATRIX/MBO: `100/100`.

Este dataset produjo 12 predictores MBO agregados, pero no mejoró la separación. No debe repetirse el mismo diseño.

### 3.2 Puerta técnica MBO con snapshot

Piloto inicial de seis sesiones:

- `12,759,652` eventos MBO.
- `256.3 MB` comprimidos.
- Snapshot `R + A + F_SNAPSHOT + F_LAST`: `6/6 PASS`.
- Contrato raw e `instrument_id`: `6/6 PASS`.
- `F_MAYBE_BAD_BOOK = 0`.
- Retrocesos de secuencia incremental: `0`.
- Reconciliación interna MBO mínima: `100.0000%`.
- Censura izquierda máxima: `0.0000%`.
- Niveles atacados `L0:L2` reconstruibles en `t_burst`: `6/6 PASS`.
- Cutoff causal antes de `t_decision`: `6/6 PASS`.
- Eventos posteriores usados: `0`.

Los 946 aparentes retrocesos de secuencia pertenecían exclusivamente a los `A` sintéticos del snapshot, ordenados por prioridad de cola y con secuencias históricas. Los incrementales reales no tuvieron retrocesos.

### 3.3 Muestra snapshot ampliada

- Las 100 sesiones MBO con snapshot ya fueron descargadas.
- El experimento ciego produjo 98 casos utilizables.
- No hace falta descargar MBO adicional ni ejecutar ATAS para iniciar V2.
- Conservar la protección de disco: dejar al menos `10 GB` libres.

### 3.4 Aclaración sobre ATAS/Rithmic y footprint

La coincidencia del footprint ATAS/Rithmic con Databento **no es una puerta de validez**. Los precios normalmente coinciden, pero el footprint puede no hacerlo.

Para este estudio:

- DOM, tape, cola, fills y cancelaciones se reconstruyen internamente desde el mismo MBO de Databento.
- El BBO MBO define el nivel atacado.
- El precio ATAS es solamente informativo.
- No mezclar relojes o volúmenes de proveedores para reconstruir causalmente un mismo evento.

---

## 4. Resultado del baseline MATRIX + MBO anterior

Discovery:

- 100 sesiones: `A=29`, `B=41`, `C=30`.
- Ajuste A/B limpio: `n=70`.
- LOYO: 2022/2023/2024.
- Causalidad MATRIX: `PASS`.

| Bloque | BA | AUC | p | Resultado |
|---|---:|---:|---:|---|
| MATRIX_SEQUENCES | 0.550 | 0.483 | 0.2168 | FAIL |
| MATRIX_TRANSITIONS | 0.542 | 0.597 | 0.2757 | FAIL |
| MATRIX_TRANSITIONS_SEQUENCES | 0.495 | 0.529 | 0.5275 | FAIL |
| MATRIX_TRANSITIONS + MBO_CORE | 0.490 | 0.503 | 0.5524 | FAIL |
| MATRIX_TRANSITIONS_SEQUENCES + MBO_CORE | 0.478 | 0.471 | 0.6034 | FAIL |
| MBO_CORE | 0.439 | 0.451 | 0.8082 | FAIL |
| MATRIX_SEQUENCES + MBO_CORE | 0.434 | 0.428 | 0.8182 | FAIL |

Aporte incremental de MBO:

- Transitions + MBO frente a Transitions: `BA -0.052`, `AUC -0.094`.
- Sequences + MBO frente a Sequences: `BA -0.116`, `AUC -0.055`.
- Transitions+Sequences+MBO frente al bloque sin MBO: `BA -0.017`, `AUC -0.058`.

**Conclusión:** los 12 agregados MBO originales no representan adecuadamente la dinámica causal. El problema no se resuelve comprando más fechas bajo esa misma representación.

---

## 5. Experimento ciego perceptual: resultados y hashes

Directorio:

`C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_codex_claude\human_blind_v1`

### 5.1 AMD-1

- 98 renders causales DOM+tape de `0–5 s`.
- Orientación BUY canónica.
- Sin fecha, outcome, lado absoluto ni mapping visibles.
- Ventana: `[strict_feature_cutoff, cutoff + 5s)` por `ts_recv`.
- Un paquete se aplica únicamente al llegar `F_LAST`.
- Si `F_LAST` cae en o después del límite derecho, el paquete completo se excluye.

Split temporal congelado antes de outcomes:

- Discovery 2022–2023: `n=69`.
- Validación 2024: `n=29`.
- SHA-256 del split:

  `862e7041d7d4cd3ad2aa3588f7eeafa504e1b3b76cfd4f87b88f4dc2d0f8f664`

Etiquetas:

- Eduardo: `A39/B37/C22`.
  - SHA-256: `72f945c1195a070b4f5e93f57c3cbe6ffc5020d504ffe74098c37fdefd21886f`
- Claude: `A30/B38/C30`.
  - SHA-256: `c48535384452444fa81eee08ba593418eeef37ce16cab7811d668008d0d7a1b7`
- Codex: `A35/B37/C26`.
  - SHA-256: `413a82d472e3897de270698762a8f4a0675ce67a8102bb45790761611bb08e32`

Concordancia:

- Tres codificadores: alpha `0.439623` frente al gate `0.60` → `FAIL`.
- Eduardo–Claude: acuerdo `52.04%`, kappa `0.2767`.
- Eduardo–Codex: acuerdo `53.06%`, kappa `0.2842`.
- Claude–Codex: acuerdo `83.67%`, kappa `0.7538`, alpha `0.7546`.

### 5.2 AMD-2

Regla de consenso ordenada por el usuario:

- `A/A → A`
- `B/B → B`
- cualquier otro caso → `C/abstain`

Consenso original:

- `A=27`, `B=35`, `C=36`.
- Casos direccionales: `62`.
- Acuerdo direccional Claude–Codex: `62/62`.
- SHA-256:

  `d3ca0d8238b0698b913dbe4b782f99076691027b886f96a416a3e15152b971a3`

Perturbación cosmética 1:

- Gate congelado: máximo `10%` de cambios entre los 62 A/B originales.
- Resultado: `9/62 = 14.516%` → `FAIL`.
- Transiciones: `A→A 20`, `A→C 7`, `B→B 33`, `B→C 2`, `C→A 7`, `C→C 29`.
- Inversiones `A↔B`: `0`.
- SHA-256 del resultado:

  `cee7958d5ae375da7a998761f394153cb92ee6f52313ce74e16e828517c1130d`

### 5.3 AMD-3

Stable Core outcome-blind:

- A si original=A y perturbación1=A.
- B si original=B y perturbación1=B.
- En cualquier otro caso C.
- Resultado: `A=20`, `B=33`, `C=45`.
- Denominador direccional: `53`.
- SHA-256:

  `a9ed1568d5274a6b881aac00d74c8022da253af25da329ed809900708b80e68e`

Perturbación cosmética 2:

- Gate congelado: máximo `10%` de cambios sobre los 53 A/B.
- Resultado: `7/53 = 13.2075%` → `FAIL`.
- Transiciones: `A→A 13`, `A→C 7`, `B→B 33`, `C→A 5`, `C→B 3`, `C→C 37`.
- Inversiones `A↔B`: `0`.

Hashes:

- Resultado JSON:

  `32377174d04f9773dd24191748fbc44729100c8089938632833ae1ff2e377af1`
- CSV de 98 casos:

  `f4cc303032436be51a6aadafd42f870324bb9c0b9ff5a044c2ed61445061a667`
- Claude AMD-3:

  `0031255c285cd79a098691a6ade7639db0911ca790fd1bb291b91782a5fe9920`
- Codex AMD-3:

  `00b4a8298ea9cf57ac9fca97c1c4863bedaf4648390dbeebfbc056ce6154090c`

---

## 6. Qué quedó cerrado y no debe repetirse

1. No ejecutar más recodificaciones cosméticas sobre los mismos 98 renders.
2. No ajustar retrospectivamente el umbral de `10%`.
3. No eliminar `C` después de haber visto el fallo.
4. No abrir outcomes para “ver qué pasa” antes de congelar V2.
5. No entrenar otro clasificador con los mismos 12 agregados MBO.
6. No descargar más sesiones para compensar una representación inestable.
7. No ejecutar ATAS ni repetir replay para construir la primera versión de V2.
8. No interpretar las cero inversiones A↔B como prueba de capacidad predictiva.
9. No seleccionar pesos, ventanas o features por su relación con MFE, MAE, TP, SL, PnL o la familia futura.
10. No usar datos de 2024 para normalizar o diseñar; 2024 continúa como validación confirmatoria cerrada.

---

# 7. NEXT STEPS PRIORITARIOS

## Fase V2-0 — Recuperar y verificar el estado congelado

- [ ] Leer este handoff y el documento:

  `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_codex_claude\20260725_034_CIERRE_AMD3_REPRESENTACION_PERCEPTUAL.md`

- [ ] Verificar los hashes de AMD-2/AMD-3 y del split antes de trabajar.
- [ ] Confirmar que mapping/outcomes siguen sin abrirse.
- [ ] Usar una nueva carpeta `mbo_continuous_v2`; no alterar artefactos AMD.

Artefactos principales:

- `...\human_blind_v1\amd2_stability\audit\AMD2_STABILITY_RESULT.json`
- `...\human_blind_v1\amd3_stability\audit\AMD3_STABILITY_RESULT.json`
- `...\human_blind_v1\amd3_stability\audit\AMD3_STABILITY_CASES_98.csv`
- `...\human_blind_v1\amd3_stability\audit\AMD3_RESULT_HASHES.sha256`

## Fase V2-1 — Convergencia Claude + Codex y preregistro

Antes de ejecutar cálculos de outcome:

- [ ] Claude y Codex deben proponer por separado la fórmula V2.
- [ ] Comparar propuestas y crear una especificación convergente.
- [ ] Congelar en un MD:

  - nombres exactos de componentes;
  - ecuaciones;
  - orientación de signo;
  - unidades;
  - normalización;
  - tratamiento de faltantes;
  - ventanas temporales;
  - cobertura mínima;
  - fórmula del score;
  - métrica separada de incertidumbre;
  - perturbaciones de estabilidad;
  - gates;
  - único endpoint discovery compatible con score continuo;
  - condición exacta para abrir 2024.

- [ ] Hashear el preregistro antes de evaluar estabilidad.

**No usar las etiquetas perceptuales fallidas como target para elegir pesos.**

## Fase V2-2 — Extraer componentes mecánicos causales

Construir una tabla temporal por caso usando solamente eventos con paquete completo anterior al límite causal. La ventana inicial permanece en `0–5 s` después del cutoff, salvo que Claude+Codex congelen otra regla antes de outcomes.

Componentes candidatos que deben evaluarse mecánicamente:

1. **Duración de aceptación sobre L0**  
   Fracción causal de la ventana durante la cual el BBO/precio permanece más allá del nivel atacado.

2. **Desplazamiento terminal canónico**  
   Distancia final desde L0 en ticks, orientada para que aceptación/breakout tenga signo positivo.

3. **Área firmada del desplazamiento/BBO**  
   Integral temporal del desplazamiento canónico; distingue un toque fugaz de una aceptación sostenida.

4. **Ciclos de cruce y reclaim de L0**  
   Número, duración y orden de cruces/reclaims.

5. **Tiempo a primera aceptación durable**  
   Definir “durable” mecánicamente antes de outcomes.

6. **Último reclaim y hold terminal**  
   Tiempo del último reclaim y duración del estado final.

7. **Fill pasivo normalizado por `Q0`**  
   Contratos ejecutados contra la liquidez defensora / profundidad inicial atacada.

8. **Refill posterior al fill**  
   Ratio y latencia de reposición después de ejecuciones, distinguiendo orden sobreviviente, modificación y orden nueva cuando el MBO lo permita.

9. **Adds menos cancels bajo agresión**  
   Por L0/L1/L2 y lado atacado/defensor, normalizado sin outcome.

10. **Supervivencia de órdenes/cola bajo agresión**  
    Identidad MBO, tiempo de vida, volumen que permanece, cancelaciones delante y reemplazo.

11. **Migración o cesión del libro**  
    Velocidad/slope con que la liquidez defensora se repone, migra o abandona niveles.

12. **Tape alineado frente a counterflow**  
    Volumen agresor alineado con el burst contra volumen contrario, sincronizado desde la misma fuente MBO.

Toda normalización temporal debe ajustarse únicamente con los inputs de discovery 2022–2023 y aplicarse congelada a 2024. No usar distribución de 2024 para diseñar ni escalar.

## Fase V2-3 — Score continuo y cobertura separada

Crear:

- `S_defensa_aceptacion`: score continuo.
  - Extremo defensa/absorción: signo negativo.
  - Extremo aceptación/breakout: signo positivo.
- `Q_cobertura`: calidad/cobertura del cálculo, separada del score.

No volver a crear una clase subjetiva `C`. La incertidumbre debe expresarse como:

- magnitud cercana a cero;
- cobertura insuficiente;
- intervalo o sensibilidad del score;
- pero no como una tercera familia escogida visualmente.

Ponderación permitida antes de outcomes:

- componentes con signo teórico;
- estandarización robusta;
- pesos iguales;
- score latente/monótono congelado;
- calibración con secuencias sintéticas de comportamiento conocido o nuevas ventanas completamente outcome-blind.

Ponderación prohibida:

- maximizar AUC/BA sobre outcomes;
- seleccionar features por MFE/MAE;
- ajustar pesos contra las etiquetas visuales AMD fallidas;
- probar muchas variantes y conservar la mejor.

## Fase V2-4 — Puerta de estabilidad sin outcomes

Perturbar solamente la representación o resolución, nunca la semántica:

- granularidad temporal;
- orden de presentación;
- redondeo inocuo;
- pequeñas variantes deterministas del muestreo;
- reconstrucción equivalente por paquetes completos.

Claude+Codex deben congelar antes de ejecutar:

- correlación de rangos mínima entre scores;
- máximo de cambios de signo fuera de una banda neutra predefinida;
- tolerancia de error absoluto normalizado;
- cobertura mínima;
- criterio conjunto `PASS/FAIL`.

La banda neutra es una tolerancia numérica del score, no una nueva etiqueta aprendida.

Si V2 falla estabilidad:

- no abrir outcomes;
- documentar la causa;
- usar nuevos estímulos sintéticos/outcome-blind o rediseñar la medición;
- no repetir perturbaciones hasta obtener casualmente un PASS.

## Fase V2-5 — Una sola prueba discovery

Sólo si V2 pasa la puerta de estabilidad:

- Abrir discovery 2022–2023 una sola vez (`n=69`).
- No abrir 2024 durante diseño.
- No abrir 2025–2026.

El endpoint previo para clases duras era:

`delta = E[MFE_ticks / OR_ticks]_A - E[MFE_ticks / OR_ticks]_B`

con bootstrap por sesión de `10,000` repeticiones y éxito si:

- el IC95 excluye `0`; y
- `|delta| ≥ 0.25`.

**Advertencia decisiva:** V2 será continuo; no se puede reutilizar silenciosamente un endpoint categórico. Antes de abrir outcomes, Claude+Codex deben preregistrar **un único endpoint continuo compatible**, por ejemplo:

- asociación monótona predefinida entre score y desplazamiento futuro normalizado; o
- contraste determinista entre colas extremas congeladas.

No registrar múltiples endpoints para luego escoger el favorable.

## Fase V2-6 — Validación confirmatoria

Únicamente si discovery pasa exactamente el gate congelado:

- abrir 2024 una sola vez;
- aplicar sin cambios fórmula, normalización, pesos, cobertura y endpoint;
- exigir estabilidad por BUY/SELL y por año sin recalibrar;
- mantener 2025–2026 cerrado hasta completar esta confirmación.

Si 2024 falla, el resultado es `NO VALIDADO`; no se corrige el modelo usando 2024 y se vuelve a presentar como confirmación.

---

## 8. Árbol de decisión resumido

```text
MBO snapshot existente
        |
        v
Claude + Codex congelan V2 mecánico continuo
        |
        v
Extracción causal 0–5 s, paquetes F_LAST
        |
        v
Estabilidad outcome-blind
   | FAIL                 | PASS
   v                      v
No abrir outcome       Discovery 2022–2023 una vez
Rediseñar medición        | FAIL             | PASS
                          v                  v
                       Cerrar V2       Validación 2024 una vez
                                             |
                                    2025–2026 sigue cerrado
```

---

## 9. Archivos y repositorio congelado

Documento de cierre:

`C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_codex_claude\20260725_034_CIERRE_AMD3_REPRESENTACION_PERCEPTUAL.md`

Repositorio aislado:

`C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_codex_claude\human_blind_v1\frozen`

Branch:

`codex/humanblind-v1-freeze`

Commits/tags:

- `2ab16c3` — `humanblind-v1.1` — AMD-1 sin espera artificial.
- `23f3d46` — `humanblind-v1.2` — AMD-2.
- `6c4f752` — `humanblind-v1.2-inputs`.
- `9f3a01e` — `humanblind-v1.3`.
- `5198dc9` — `humanblind-v1.3-inputs`.

Existe un `__pycache__` sin seguimiento en el repositorio congelado. Debe ignorarse y preservarse; no limpiar ni resetear el worktree.

---

## 10. Prompt recomendado para iniciar el nuevo chat

```text
Lee completamente:
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_codex_claude\HANDOFF_LIQUIDITY_BURST_MBO_V2_NEXT_STEPS_20260725.md

Continúa desde la Fase V2-0. El objetivo único es separar causalmente ABSORCIÓN LIMPIA de BREAKOUT LIMPIO después de un Liquidity Burst.

No abras mapping/outcomes, no ejecutes ATAS, no descargues más MBO y no uses MFE/MAE/TP/SL/PnL para diseñar features. Primero verifica los artefactos congelados y sus hashes. Después dialoga con Claude Fable y lleguen a una especificación convergente, preregistrada y hasheada para un score continuo mecánico defensa–aceptación y su gate de estabilidad outcome-blind.

No repitas la clasificación perceptual A/B/C. Si el score no pasa estabilidad, no abras discovery. Si pasa, preregistra un único endpoint continuo y abre discovery 2022–2023 una sola vez; 2024 y 2025–2026 deben continuar cerrados hasta que corresponda.

Documenta cualquier hallazgo en contexto_codex_claude y envía a Telegram el resultado, integridad causal, veredicto y next steps.
```

---

## 11. Estado exacto al entregar este handoff

- Datos MBO snapshot: disponibles.
- ATAS/replay requerido para comenzar V2: no.
- Mapping abierto: no.
- Outcomes abiertos: no.
- Discovery 2022–2023 ejecutado sobre AMD/V2: no.
- Validación 2024 abierta: no.
- 2025–2026 abierta: no.
- Representación perceptual A/B/C: cerrada por inestabilidad.
- Próxima acción autorizable: diseñar y preregistrar V2 mecánico continuo con convergencia Claude+Codex.
