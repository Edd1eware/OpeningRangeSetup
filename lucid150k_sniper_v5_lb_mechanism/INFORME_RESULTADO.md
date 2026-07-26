# Resultado — LUCID150K-SNIPER-V5-LB-MECHANISM

Fecha: 2026-07-26  
Prerregistro:
`3887e468ff4147790eb03da30f99caa9f45c2f736a5883768b1ba748645f2f87`  
Veredicto: **FAIL_NO_HOLDOUT**

## Integridad

- 96 primeros eventos elegibles, versión v7.
- 2024 excluido por diseño.
- 0 errores de cálculo.
- 2 fechas sin NQ local.
- 59 eventos excluidos por riesgo fuera de 20..80 ticks.
- 2 ambiguos.
- 33 trades entre DEV y bloque descriptivo.

## DEV

| Familia | n | EV | PF | Años + | Semestres + | PASS |
|---|---:|---:|---:|---:|---:|---|
| Continuation acceptance | 16 | +0.30467R | 1.9175 | 2/2 | 75% | No: n<18 |
| Absorption reclaim | 4 | +0.36098R | 1.6423 | 1/2 | 66.7% | No: n<18 y estabilidad |

Continuation pasó todos los gates económicos y temporales salvo tamaño muestral.
No se reduce retrospectivamente `n>=18`.

## Falsificación temporal descriptiva 2025–2026

No fue gate porque ninguna familia pasó DEV:

```text
continuation: n=3, EV +0.278R, solo 2025
absorption:   n=10, EV +0.289R,
              2025 -0.552R, 2026 +1.549R
```

La continuation no tiene frecuencia comparable y absorción cambia de signo
entre años. No existe base para holdout ni simulación Lucid.

## Hallazgo

Esperar cinco barras y exigir aceptación parece aumentar la calidad del LB,
pero el stop al midpoint y el límite 20..80 dejan una muestra demasiado pequeña
para un sistema que deba pasar 150K en 63 sesiones. Es una pista de investigación,
no un edge operativo.

SHA-256:

- resultado:
  `23F2B38784E8D2AB8BFB0845918EA62C6BBE7FE8A47CB12EFB51E650018A437A`;
- trades:
  `5BDD9C37E0F9FC6C0A995872FCAB8111E1CFED624A8261ABDBA85C8EF6150625`.

`INFORMATION_STATUS=LUCID150K_SNIPER_V5_FAIL_PROMISING_BUT_UNDERPOWERED`
