# Convergencia Claude Fable–Codex — cierre V1 y siguiente vía

Fecha: 2026-07-24  
Estado: **CONVERGENCIA FINAL**

## 1. Cierre de Mechanical Book V1

Mechanical Book V1 queda cerrado por los gates prerregistrados:

- A=2 y B=2, ambos por debajo de 15%;
- ausencia de ambas clases en cada año;
- ausencia de ambas clases en cada lado;
- Jaccard B=.667/.500 <.70.

No se ajustan `h`, cinco segundos, L0, reglas ni población. No se entrena
clasificador y no se compran datos para rescatar este diseño.

## 2. Semántica F/C

El dato MBO es válido. `F` no muta el libro; una actualización `M` o `C`
refleja la mutación, y el estado se evalúa después de `F_LAST`.

La puerta `fills_reconciled_with_C`:

- no estaba en el preregistro;
- trataba incorrectamente los fills parciales `F+M`;
- no entendía reposición/iceberg;
- queda degradada a diagnóstico en una errata inmutable.

Además, seis contratos eran `F` de la propia orden agresora. Es un defecto
menor de `F_dep`; las cuatro sesiones afectadas continúan C en base y
sensibilidades. V1 no se reetiqueta.

## 3. Test Cero histórico retirado

Claude y Codex retiran conjuntamente el Test Cero propuesto en los borradores
`PREREGISTRO_AB_ORB_NQ.md` y `RUNBOOK_AB_ORB_NQ.md`.

Las familias A=29/B=41 se construyeron con `Result_Label`, MFE y MAE.
Contrastar MFE entre ellas es circular. Desde ahora:

```text
A=29/B=41 -> OUTCOME_DERIVED_NEVER_GROUND_TRUTH
```

## 4. No existe otra prueba válida con los datos etiquetados actuales

- Mechanical V1: n=2/n=2 y gates fallidos.
- Price Taxonomy V5: gates fallidos y línea cerrada.
- Elegir ahora otra combinación de los diagnósticos ya observados sería
  post hoc.
- Correlacionar variables mecánicas post-decisión con precio post-decisión no
  crea ground truth ni demuestra anticipación.

La línea “validar la taxonomía con las etiquetas existentes” queda cerrada.

## 5. Única vía nueva propuesta al usuario: HUMAN_BLIND_V1

Esta vía requiere autorización específica del usuario. No está iniciada.

### Población y material

- mismas 98 sesiones MBO 2022–2024;
- un `BurstId` por observación;
- render local de libro L0:L9 y tape sólo en
  `[strict_cutoff, strict_cutoff+5s)`;
- nada posterior a cinco segundos;
- precios en ticks relativos a L0;
- fecha, año, símbolo y `BurstId` ocultos;
- SELL espejado para presentar todos los ataques en la misma orientación;
- orden aleatorio con semilla congelada.

### Ground truth humano

- Eduardo etiqueta cada render una vez como A absorción limpia, B breakout
  limpio o C no clasificable;
- la rúbrica se escribe, hashea y congela antes de mostrar el primer render;
- segunda ronda completa después de al menos siete días, con nuevo orden
  aleatorio;
- no se muestran MFE, MAE, TP, SL, PnL ni resultado.

### Gates congelables

- Cohen kappa test-retest >=.70;
- A>=15% y B>=15% de clasificables;
- A y B presentes en 2022, 2023, 2024;
- A y B presentes en BUY y SELL;
- C/no clasificable <=50%.

Si falla cualquier gate, el fenómeno no es identificable de manera
reproducible en esta representación de cinco segundos y la línea se cierra.

Sólo si pasa todos los gates se permite una validación outcome única:

```text
endpoint = E[MFE_ticks/OR_ticks]_A - E[MFE_ticks/OR_ticks]_B
incertidumbre = block bootstrap por sesión, 10,000 réplicas, IC95%
MDE = 0.25
éxito = IC95% excluye cero y |delta| >= 0.25
```

MFE/MAE siguen siendo outcome posterior, nunca predictor ni parte de la
etiqueta.

## 6. Puntos no negociables

- Ningún gate prerregistrado se relaja post hoc.
- No descargar MBO, no entrenar clasificador, no lanzar ATAS y no tocar
  2025–2026 antes de que exista un instrumento válido.
- El etiquetado humano no comienza sin autorización específica.
- La exposición previa del etiquetador a algunas sesiones se documentará
  como limitación; la anonimización la mitiga, no la elimina.
- Toda desviación será append-only.

Firmado: Claude Fable + Codex

