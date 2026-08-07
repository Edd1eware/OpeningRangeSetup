# Auditoría trade-only de las primeras 60 fechas

Fecha: 2026-07-27

Estado: `MECHANICAL_DESCRIPTIVE_AUDIT_ONLY`

Esta corrida no calcula régimen, outcomes, features, modelos, bootstrap ni PnL.
Su resultado no puede modificar ningún umbral.

## Definición literal del gate LB

El detector requiere, para BUY o su espejo SELL:

```text
baseline_ready: history >= 30 s
direction * Delta1s > 100
direction * DeltaChange1s > 75
direction * DeltaChangeZScore >= 2.5
DeltaPercentile >= 0.95
TradesPerSecond >= 5
ContractsPerSecond >= 50
direction * CumulativeDelta3s >= 150
RequirePriceVelocity = false
detection window = 09:30:00..16:00:00 NY
same-side cooldown = 5 s
```

## Resultado

- fechas: 2022-04-04 a 2022-06-24;
- fechas intentadas: 60;
- sesiones trade legibles: 57;
- sesiones trade excluidas: 3;
- sesiones legibles con al menos un LB:
  57;
- LB trade-only: 1868;
- mínimo/máximo por sesión legible:
  7/
  85;
- sesiones con depth/MID válido: 0;
- referencias MID válidas posibles: 0.

El `0 LB válidos` del progreso anterior no significaba que el detector no
disparara. El `except Exception` reemplazó el conteo por cero después de fallar
depth. El defecto es de datos/instrumentación: no hay depth utilizable en
ninguna de las primeras 60 fechas.

La tabla completa está en `trade_only_first60.csv`.

`INFORMATION_STATUS=TRADE_ONLY_FIRST60_MECHANICAL_AUDIT_COMPLETE`
