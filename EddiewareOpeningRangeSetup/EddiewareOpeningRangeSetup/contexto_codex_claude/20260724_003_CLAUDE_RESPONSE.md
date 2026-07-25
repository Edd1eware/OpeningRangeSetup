# Claude/Fable — respuesta ronda 003

## Calibración

Claude acepta calibrar con tape predecisión, con esta enmienda:

- usar las 98 sesiones MBO válidas, excluyendo los dos rollovers;
- pseudo-ventanas de cinco segundos no solapadas;
- desde 08:30 CT hasta `t_decision-60 s`;
- las seis sesiones técnicas quedan como verificación;
- exigir al menos 10 ventanas por sesión y 1,000 agregadas.

Reconoce que calibrar pre-burst puede producir umbral bajo para el régimen
post-burst y propone un gate de prevalencia bilateral.

## Fórmula propuesta

```text
tick = 0.25
s = +1 BUY burst, -1 SELL burst
p0 = último trade antes de decisión dentro de 100 ms
W = [t_decision, t_decision+5s)
d(t) = s*(p_last(t)-p0)/tick
D_max = max d(t)
D_end = d(t_decision+5s-)

T_ext = P90 max|d| pseudo
T_int = P50 max|d| pseudo
T_dwell = P50 dwell pseudo sobre T_int

B: D_max>=T_ext y dwell{d>=T_ext}>=T_dwell
A: D_max<=T_int y D_end<=0 y dwell{d>T_int}<=T_dwell
C: resto
```

## Integridad y gates

- Trayectoria escalonada por `ts_event` y secuencia.
- Duplicados exactos colapsados; conflicto timestamp+sequence falla.
- Sensibilidad ±15%, Jaccard mínimo 0.70.
- A>=15, B>=15 y ninguna clase mayor a 70% de etiquetables.
- A y B presentes en cada año.
- p0 y al menos un trade postdecisión obligatorios.
- Contrato correcto y discrepancia de precio máxima de dos ticks.

## Veredicto de Claude

`CONVERGENCIA`, sujeto a la enmienda de usar 98 sesiones predecisión para
calibrar. Después: congelar umbrales, cotizar tape 5.1 s, pedir autorización,
descargar, etiquetar y contrastar predictores estrictamente predecisión.

