# Errata de alcance: A1 equivalence

Fecha: 2026-07-27

`artifacts/equivalence/A1_equivalence.json` compara la implementación Python
actual contra caches Python previos por sesión. Su alcance correcto es:

```text
PYTHON_TO_PYTHON_EXACT_REGRESSION
```

No demuestra paridad completa entre `12_LiquidityBurstDetector.cs` y el port
Python. El nombre físico del archivo se conserva para no romper rutas ni
evidencia histórica.

La paridad C#↔Python queda como deuda técnica:

- no bloquea la auditoría científica target-only local;
- sí bloquea cualquier afirmación de identidad con el indicador ATAS y
  cualquier despliegue posterior en ATAS.

`INFORMATION_STATUS=A1_SCOPE_CORRECTED_NO_FILE_RENAME`
