# Enmienda técnica A1: timestamps y rendimiento

Fecha: 2026-07-26

Estado: `AFTER_SMOKE_BEFORE_DISCOVERY`

Esta enmienda se redacta después del smoke de cinco fechas y antes de abrir
discovery. No cambia ninguna definición predictiva.

## Evidencia preservada

Freeze original:

- copia: `FREEZE_MANIFEST_PRE_SMOKE_V1.json`;
- SHA-256 de la copia:
  `4C9CE264B8DC00285F3E9CD5B10275A900768EBA5E5BB7483F026F8820A8AC56`.

Smoke original:

- sesiones PASS: 4/5;
- LB: 80;
- candidatos válidos: 16,160;
- causalidad: PASS;
- intersección outcome/predictor: vacía;
- `SNIPER_SUCCESS`: 0;
- resultado: FAIL técnico por un timestamp no monótono en 2022-08-02.

Hashes del smoke original:

- `data_audit.csv`:
  `F414DA5906699538E663EFAFBC4375D1E7F364E08813289E138A0BC018194202`;
- `liquidity_bursts.csv`:
  `4FCF29AB5205F4D1F3947F15EF1A195FCD21E9EDC333B5049C1C4D785A699254`;
- `vt_candidates.parquet`:
  `5A37CC98450C54629BC36F49C1BEB797B1A808944956E37B01788A469DFCB25F`;
- `result.json`:
  `7FED31632E6A762DB4E2074683FF7D238550C7B97A43024B475B063A2AA354E1`.

Los artefactos se copiaron a `artifacts/equivalence/reference_smoke_v1`.

## Diagnóstico outcome-blind de timestamps

Se recorrieron las 195 fechas hábiles previstas para discovery sin calcular
features, outcomes ni métricas predictivas:

- 189 sesiones legibles;
- 66 sesiones con algún retroceso;
- 9,665 retrocesos totales;
- 60/66 sesiones afectadas tienen sólo 1 a 3 retrocesos;
- el régimen leve termina en 31 ms;
- cinco sesiones tienen 499 a 6,112 retrocesos;
- una sesión contiene un retroceso de 222.135 s;
- seis fechas son ilegibles o no tienen archivo, principalmente feriados.

La evidencia está en:

- `artifacts/qc/discovery_timestamp_audit.csv`;
- `artifacts/qc/discovery_timestamp_summary.json`.

## Regla causal congelada A1

El orden de archivo se considera el orden de llegada disponible. No se ordenan
trades usando timestamps futuros.

Para una sesión con:

- `backtrack_count <= 10`; y
- `largest_backtrack_ms <= 50`,

se define secuencialmente:

```text
EffectiveTimestamp_0 = RawTimestamp_0
EffectiveTimestamp_i =
    max(EffectiveTimestamp_i-1, RawTimestamp_i)
```

Esto sólo retrasa el timestamp efectivo del trade fuera de orden y nunca lo
adelanta. El orden de filas, precio, lado y volumen permanece intacto.

Si cualquiera de los dos límites se excede, se excluye la sesión completa.
Los límites fueron elegidos sobre la distribución de integridad, sin consultar
outcomes o PnL.

## Enmienda mecánica de rendimiento

El profiler outcome-blind sobre un LB mostró:

- 202 candidatos en 23.594 s;
- 22.363 s dentro de `numpy.searchsorted`;
- causa: búsquedas repetidas sobre la vista estructurada no contigua de ticks.

A1 crea una copia contigua de timestamps efectivos una vez por sesión y la
reutiliza en todas las búsquedas. No cambia límites de ventana ni contenido de
filas.

Puerta de aceptación:

1. tests de causalidad y simetría PASS;
2. timestamp pequeño se corrige sin adelantar filas;
3. timestamp fuera de límites excluye la sesión;
4. en sesiones originalmente monótonas, salida optimizada igual a referencia
   columna por columna, admitiendo sólo igualdad numérica dentro de tolerancia
   de máquina;
5. detector, outcome y thresholds conservan los mismos hashes lógicos del
   prerregistro salvo los cambios técnicos aquí descritos.

Si falla la equivalencia, la optimización no puede abrir discovery.

Resultado de equivalencia antes del nuevo freeze:

- tests sintéticos: 6/6 PASS;
- sesiones reales: 4/4 `EXACT_PASS`;
- LB comparados: 80;
- candidatos comparados: 16,160;
- igualdad: columna por columna y LB por LB;
- tiempo reconstrucción A1: 48.65 s para las cuatro sesiones;
- referencia original: aproximadamente 34 min;
- artefacto: `artifacts/equivalence/A1_equivalence.json`.

## Outcome primario

El smoke reveló `SNIPER_SUCCESS=0`. La auditoría mostró que el gate restrictivo
es `FutureDirectionalEfficiency_2s >= 0.65`; su fórmula coincide con la
especificación entregada.

Estado congelado:

```text
PATH_EFFICIENCY_TRADE_V1
threshold = 0.65
DEGENERATE_TARGET_COMPONENT
```

A1 no modifica fórmula ni umbral. Se permite crear `SNIPER_CORE`, definido sólo
por los otros cinco gates, exclusivamente como diagnóstico técnico y nunca como
target de entrenamiento.

Antes de discovery se preregistrará una auditoría outcome-only separada de
eficiencias basadas en trades, mid, microprice, excursión y retención. Ninguna
variante podrá elegirse por maximizar positivos.

Validation 2023, holdout 2024 y 2025–2026 permanecen sellados.
