# Test Cero retirado — circularidad de las familias A/B históricas

Fecha: 2026-07-24  
Decisión conjunta: Claude Fable + Codex  
Estado: **NO EJECUTAR**

## Evidencia

Las familias históricas usadas en el análisis MATRIX/MBO (`A=29`, `B=41`,
`C=30`) no son ground truth independiente. La función
`absorption_breakout_research.py::_label_family` las define con el outcome
terminal:

```text
A_TRUE_ABSORPTION:
  Result_Label == TP
  AND MAE_ticks <= 10
  AND MFE_ticks >= Initial_TP_ticks

B_CLEAN_BREAKOUT:
  Result_Label == SL
  AND MFE_ticks <= 10
  AND MAE_ticks >= Initial_SL_ticks
```

Por lo tanto, contrastar después `MFE/OR` entre A y B mediría la regla que creó
las clases. La diferencia estaría inducida por construcción y no demostraría
que el DOM, tape o MBO distinguen absorción de breakout.

## Decisión

- `PREREGISTRO_AB_ORB_NQ.md` y `RUNBOOK_AB_ORB_NQ.md` permanecen como
  borradores históricos, no congelados.
- Su Fase 0 no se ejecuta.
- A=29/B=41 se marca:

```text
OUTCOME_DERIVED_NEVER_GROUND_TRUTH
```

- Estas etiquetas pueden describir trayectorias terminales y servir como
  outcome de clasificación exploratoria pasada, pero no validan una nueva
  taxonomía ni un Test Cero con MFE/MAE.

No se lanzó ATAS, no se entrenó modelo y no se descargaron datos.

