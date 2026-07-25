# Resultado del nuevo enfoque FMD — Gate Cero de accionabilidad

Fecha: 2026-07-24  
Estado: **INTEGRIDAD FAIL ANTES DE CALCULAR MÉTRICAS A/B**

## Qué cambió

Se revisaron:

- `C:\Users\k_99_\Desktop\fmd_files\RUNBOOK_AB_ORB_NQ.md`;
- `C:\Users\k_99_\Desktop\fmd_files\PREREGISTRO_AB_ORB_NQ.md`.

El Test Cero original no se ejecutó porque sería circular: las familias actuales
se definen con `Result_Label`, MFE, MAE, TP y SL. Compararlas nuevamente mediante
MFE/MAE no aportaría evidencia.

Se preregistró en su lugar un Gate Cero de accionabilidad: medir la diferencia
B−A en `Directional_Displacement_Ticks` durante el primer segundo posterior a
`t_decision`, sin predictores MBO.

Preregistro:

```text
PREREGISTRO_NUEVO_ENFOQUE_AB_FMD_V1_20260724.md
SHA256 0861987c50832ccb82db1c5906baf297f889f4bd919fe413166f584b80b2579b
```

Las pruebas del ejecutor pasaron 4/4.

## Resultado de integridad

- Manifiesto: 100 sesiones.
- Filas crudas de respuesta a 1 segundo: 119.
- `BurstId` distintos en esas respuestas: 118.
- Una repetición exactamente idéntica fue colapsada y registrada.
- Join con el manifiesto: 100/100.
- Sesiones sin outcome temprano: 14.
- Distribución de faltantes: A=5, B=4, C=5.
- Por año: 2022=4, 2023=5, 2024=5.
- No existen copias alternativas de esas respuestas en las corridas locales.

Como el preregistro exigía cobertura completa, el programa terminó con
`INTEGRIDAD_FAIL`. No se calculó la diferencia A/B, el bootstrap, la permutación
ni la potencia. Por tanto, todavía no existe un resultado favorable, negativo o
no concluyente del Gate Cero.

## Por qué no se deben usar sólo 86 sesiones

Eliminar las 14 filas según disponibilidad del exportador introduciría una
selección posterior al diseño. Aunque los faltantes estén repartidos entre
familias y años, no se demostró que sean aleatorios. Usar 86 casos sólo podría
ser un diagnóstico exploratorio y no habilitaría trabajo MBO.

## Reparación defendible

Construir el endpoint uniformemente para las 100 sesiones desde el tape
`trades` de Databento:

```text
inicio = t_decision - 100 ms
fin exclusivo = t_decision + 1 s
```

La fracción previa proporciona el último precio causal de referencia. Las dos
sesiones con rollover conocido deben solicitar el contrato que coincide con
ATAS:

- 2022-06-13: NQU2, no NQM2;
- 2023-06-13: NQU3, no NQM3.

Una muestra de consultas `metadata.get_cost`, sin descargar datos, produjo
aproximadamente USD 0.019–0.031 por sesión. La proyección preliminar para las
100 es USD 1.9–3.1; se propone un límite de autorización de USD 3.50.

No se realizará la descarga sin autorización expresa.

## Siguiente decisión

1. Si se autoriza hasta USD 3.50, descargar tape uniforme para las 100 sesiones,
   reconstruir el endpoint y ejecutar una vez el Gate Cero congelado.
2. Si Gate Cero no da `PASS`, no volver a entrenar MBO.
3. Sólo con `PASS` se ejecutarán warm-up, nulo calibrado, sensibilidad y
   reconciliación externa sobre las seis sesiones técnicas.
4. 2025–2026 permanece cerrado.

