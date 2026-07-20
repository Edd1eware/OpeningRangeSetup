# Research ledger — Absorción vs Breakout

## Pre-registro

- Semilla: `20260717`.
- Prediction timestamp único: `feature_timestamp_utc` del snapshot de entrada.
- Familias: A TP con MAE<=10; B SL con MFE<=10 y MAE>=SL; C trayectoria mixta; D otra salida.
- Split cronológico congelado antes del análisis: 60/20/20.
- Criterio robusto: permutation q BH <0.10, |Cliff delta| >=0.33 y mismo signo en discovery, validation y holdout.
- No se busca PF, no se optimiza threshold y no se modifica trading.

## Inventario de hipótesis

- Impacto por contrato: breakout limpio debe desplazar más precio por unidad de agresión.
- Presión de absorción: absorción debe mostrar mucho delta por poco desplazamiento.
- Persistencia: breakout limpio debe conservar signo de delta y velocidad en 1/3/5s.
- Contexto: proximidad a POC/VAH/VAL/HVN/LVN puede modular absorción.
- Refill/libro: hipótesis rechazada por indisponibilidad del stream en el workspace actual.

## Holdout

- Filas totales: 184.
- El holdout se abre una sola vez al generar `final_report.md`.
- Cualquier hipótesis posterior deberá usar una temporada nueva; no se recicla este holdout.
