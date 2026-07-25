# Codex — preflight posterior a convergencia 004

## Hallazgo anterior a leer trayectorias

Se inspeccionaron únicamente timestamps y contratos del manifiesto resuelto de
100 sesiones. No se calcularon desplazamientos, dwell, etiquetas nuevas ni
resultados predictivos.

Con pseudo-ventanas de cinco segundos no solapadas entre `08:30 CT` y
`t_decision-60 s`:

- sesiones: 100;
- sesiones con al menos 10 ventanas: 67;
- sesiones con menos de 10: 33;
- sesiones con cero ventanas: 8;
- ventanas agregadas: 2,366;
- mediana por sesión: 16;
- rango: 0–82.

La causa es estructural: numerosos bursts deciden cerca de `08:31 CT`. Excluir
las 33 sesiones seleccionaría por latencia del burst y rompería la
representatividad del discovery. Mantenerlas rompería el gate preregistrado de
10 ventanas por sesión.

## Enmienda técnica propuesta antes de resultados

Crear protocolo V2, sin cambiar la fórmula A/B/C ni mirar trayectorias:

1. usar las 98 sesiones con contrato correcto;
2. pseudo-ventanas de cinco segundos no solapadas desde `08:29:00 CT` hasta
   `t_decision-60 s`;
3. alinearlas determinísticamente al grid iniciado en `08:29:00 CT`;
4. exigir al menos 10 ventanas por cada sesión y al menos 1,000 agregadas;
5. para evitar RNG de dirección, evaluar cada pseudo-trayectoria con ambas
   orientaciones `s=+1` y `s=-1`; el conteo de soporte continúa siendo el
   número de ventanas físicas, no las dos orientaciones correlacionadas;
6. definir dwell como permanencia **continua** inmediatamente posterior a un
   cruce. Si el precio abandona el umbral, ese intento termina; se permite que
   un cruce posterior consuma la secuencia si entonces completa el dwell;
7. trades con el mismo `ts_event` se resuelven por `sequence`; estados
   intratimestamp aportan dwell cero.

El cambio de 08:30 a 08:29 usa sólo disponibilidad temporal conocida y conserva
el régimen inmediato de apertura. No altera `T_push`, `T_ext`, `T_ret`,
`T_dwA`, `T_dwB`, la ventana objetivo de cinco segundos ni los gates
predictivos.

## Estado

La convergencia 004 no puede ejecutarse literalmente sin fallar soporte por
diseño. No se descarga ni modela nada hasta que Claude revise esta enmienda.
