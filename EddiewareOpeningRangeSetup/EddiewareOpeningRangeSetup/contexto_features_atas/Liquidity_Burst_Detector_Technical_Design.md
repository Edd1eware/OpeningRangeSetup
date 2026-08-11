# Liquidity Burst Detector — Technical Design Document

## Objetivo
Construir un detector causal de Liquidity Bursts para investigar si una explosión de agresión (delta por segundo + actividad + velocidad del precio) ocurre antes de una aceleración del mercado y agrega información útil para mejorar la selección de entradas del ORB.

## Principios
- Cero look-ahead
- Cero leakage
- Features congeladas al momento de decisión
- Outcomes separados
- No construir estrategia todavía
- Primero validar la hipótesis

## Arquitectura
Tape/Book -> Second Aggregator -> Aggression Features -> Velocity Features -> Liquidity Burst Detector -> Burst Snapshot (inmutable) -> Trade Input Snapshot -> Trade Outcome -> Exporter -> Excel

## Features principales
### Agresión
- Delta1s, Delta2s, Delta3s, Delta5s, Delta10s
- PeakPositiveDelta
- PeakNegativeDelta
- DeltaChange1s
- DeltaChangeZScore
- DeltaPercentile
- BuySellRatio
- TradesPerSecond
- ContractsPerSecond

### Precio
- Velocity1s
- Velocity3s
- Velocity5s
- Acceleration1s
- Acceleration3s
- TicksPerSecond

### Contexto
- OR High / Low / Width
- VWAP
- POC
- VAH
- VAL
- LVN
- HVN
- Distancias a niveles

## Detección de Burst
Detectar únicamente con información disponible hasta el segundo actual.
Implementar detectores por:
- ZScore
- Percentil causal
- Persistencia
- Delta acumulado

## Etiquetas visuales
### Verde
HIGH BUY AGGRESSION cuando:
- DeltaChange1s > 0
- DeltaChangeZScore supera umbral
- Delta1s > 0

### Roja
HIGH SELL AGGRESSION cuando:
- DeltaChange1s < 0
- DeltaChangeZScore inferior al umbral
- Delta1s < 0

No repintar.

## Integración con Exporter
Crear:
- BurstSnapshotAtDecision
- TradeInputSnapshot
- TradeOutcome

Nunca sobrescribir columnas AtEntry.

Exportar:
- trade_inputs.csv
- trade_outcomes.csv
- burst_events.csv
- burst_trade_links.csv

## Excel
Hojas:
- Trades
- Burst_Events
- Burst_Trade_Link
- Daily_Summary
- Feature_Audit
- Data_Quality
- Debug
- Config

Guardar:
BurstId, TradeId, Delta1sAtEntry, DeltaChange1s, DeltaChangeZScore,
Velocity1s, Acceleration1s, TradesPerSecond, ContractsPerSecond,
AggressionLabel, LabelColor, LabelTimestamp, Outcome, MFE, MAE.

## Anti Look-Ahead
Toda feature debe registrar:
- Timestamp
- Fuente
- Ventana
- Disponible antes de entrada

Abortar entrenamiento si alguna feature usa datos futuros.

## Tests
- Snapshot inmutable
- No repaint
- Burst BUY
- Burst SELL
- Burst sin trade
- Trade sin burst
- Reconstrucción determinista
- Anti-lookahead

## Objetivo final
No buscamos un PF alto.
Buscamos demostrar científicamente si los Liquidity Bursts agregan información incremental sobre ORB, Perfil de Volumen y VWAP.
