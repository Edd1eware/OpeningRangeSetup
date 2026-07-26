# LB-EXIT-V1 — Salir en el Liquidity Burst: RECHAZADA (3 de 4 gates)

Fecha: 2026-07-25 · Preregistro `d105142b…` · Comparación pareada, disparo único

## 1. Veredicto: FAIL

| Gate | Umbral | Obtenido | |
|---|---|---:|---|
| G1 Mejora media ≥ +2.0 ticks | ≥ 2.0 | **+2.455** | PASS |
| G2 IC95 bootstrap excluye 0 | excluye 0 | **[−9.05, +12.25]** | **FAIL** |
| G3 Mejora > 0 en ≥2 de 3 años | ≥ 2 | 2 de 3 | PASS |
| G4 n ≥ 40 | ≥ 40 | 44 | PASS |

La mejora media existe (+2.46 ticks) pero el intervalo de confianza es
**enorme y contiene el cero**. No se distingue del ruido.

## 2. Primario 2022-2024 (n=44 trades con LB durante la posición)

| | EV neto |
|---|---:|
| Mantener (trail 50/20/40) | +22.07 |
| Salir en el LB | +24.52 |
| **Mejora media** | **+2.46** |
| Mejora mediana | +10.50 |
| Trades mejorados | 65.9% |

| Year | n | Mejora media |
|---|---:|---:|
| 2022 | 12 | +8.25 |
| 2023 | 22 | +5.27 |
| 2024 | 10 | **−10.70** |

## 3. Confirmación 2025-2026 (descriptiva, sin veredicto)

| | Valor |
|---|---:|
| n | 43 |
| Mejora media | **−1.81** |
| Mejora mediana | +9.00 |
| Trades mejorados | 65.1% |

El conjunto de confirmación va en contra: mejora media **negativa**.

## 4. Lo que revela la divergencia media vs mediana

Este es el hallazgo real del test:

```text
mediana de la mejora : +10.5 (primario) / +9.0 (confirmacion)
% de trades mejorados: 66% / 65%
media de la mejora   : +2.46 / -1.81
```

**Salir en el LB mejora dos tercios de los trades, y sin embargo la media se
desploma.** La explicación es mecánica: la salida anticipada recorta muchas
pérdidas pequeñas —de ahí la mediana positiva— pero también **mata los runners
grandes**, que son los que pagan toda la estrategia de trailing.

Es la firma clásica de una regla de salida que "se siente bien" y destruye valor:
mejora la mayoría de los trades y empeora el resultado.

## 5. Cierre

Por el preregistro, un fallo = rechazada. No se prueba salida parcial, ni retardo
tras el LB, ni reversa, ni otra gestión base. La línea del LB como señal de
salida se cierra aquí.

Limitación honesta: n=44 y n=43 son muestras chicas; el test está
infra-potenciado. Pero el gate exigía IC95 excluyendo cero precisamente para no
promover ruido, y el conjunto de confirmación además apunta en contra.

`INFORMATION_STATUS=LB_EXIT_REJECTED_KILLS_RUNNERS`
