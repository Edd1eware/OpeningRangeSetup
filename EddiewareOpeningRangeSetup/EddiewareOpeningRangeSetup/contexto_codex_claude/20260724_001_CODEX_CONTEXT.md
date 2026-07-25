# Contexto Codex — ronda 001

## Objetivo invariable

Detectar un Liquidity Burst causalmente y, antes de perder la oportunidad de
entrada, anticipar si terminará como absorción limpia o breakout limpio, evitando
lookahead y sobreajuste.

## Etiquetas actuales

El código actual define:

- A si `Result_Label=TP`, `MAE<=20 ticks` y `MFE>=TP inicial`;
- B si `Result_Label=SL`, `MFE<=20 ticks` y `MAE>=SL inicial`;
- C para trayectorias restantes.

Por tanto A/B son etiquetas terminales de trayectoria/trade, no observaciones
microestructurales independientes. Comparar A/B mediante el mismo MFE/MAE sería
circular.

## Evidencia acumulada

1. MATRIX y el MBO antiguo de 12 predictores, sin snapshot:
   - A=29, B=41, C=30; A/B n=70.
   - MATRIX_TRANSITIONS BA 0.542, AUC 0.597.
   - MBO_CORE BA 0.439, AUC 0.451.
   - Los bloques combinados empeoraron y fallaron permutación/estabilidad.
2. Gate técnico MBO Snapshot sobre 6 sesiones:
   - 6/6 PASS.
   - Snapshot completo, 0 retrocesos incrementales, reconciliación interna 100%.
   - Demostró capacidad técnica, no separación A/B.
3. Expansión ya realizada:
   - 100 sesiones, 257,564,810 eventos, 5.142 GB.
   - Integridad técnica 100/100.
4. Ocho features MBO con snapshot:
   - MBO8 BA 0.485, AUC 0.511.
   - MATRIX+MBO8 BA 0.537, AUC 0.514.
   - p=0.314, mínimo año/lado BA 0.416, coherencia 4/6.
   - No mejoró MATRIX.
5. Dos rollovers contaminados en MBO:
   - 2022-06-13 NQM2 debe contrastarse con NQU2.
   - 2023-06-13 NQM3 debe contrastarse con NQU3.
   - Excluirlos post hoc no rescató el modelo.

## Aporte de los documentos FMD

Se leyeron:

- `C:\Users\k_99_\Desktop\fmd_files\RUNBOOK_AB_ORB_NQ.md`
- `C:\Users\k_99_\Desktop\fmd_files\PREREGISTRO_AB_ORB_NQ.md`

Aciertos incorporados:

- gates secuenciales;
- potencia e IC antes de declarar refutación;
- warm-up empírico;
- nulo calibrado con pseudo-eventos;
- sensibilidad a umbrales;
- reconciliación externa;
- muestra no selectiva;
- una revisión registrada.

Correcciones propuestas por Codex:

- el Test Cero MFE/MAE es circular con las etiquetas actuales;
- las 100 sesiones fueron seleccionadas por familia y no son un censo;
- pseudo-eventos deben compartir régimen de apertura;
- no definir etiquetas con las mismas features MBO usadas para separarlas.

## Gate Cero adaptado propuesto por Codex

Pregunta: ¿A y B ya divergen durante el primer segundo posterior a
`t_decision`?

Endpoint:

```text
p0 = último trade Databento con ts_event < t_decision en 100 ms previos
p1 = último trade con ts_event < t_decision + 1 segundo
Y = signo_burst * (p1-p0)/0.25
efecto = media(B)-media(A)
```

Gate PASS congelado:

- límite inferior IC95% > +1 tick;
- permutación dentro de año/lado p<=0.05;
- dirección B>A;
- bootstrap diario 10,000;
- MDE=2 ticks; potencia objetivo 0.80.

El exportador ATAS sólo contiene outcome temprano para 86/100 sesiones. Se
propuso descargar `trades` de Databento uniformemente para las 100 ventanas.

## Estado operativo al recibir la nueva regla de gobernanza

- El usuario había autorizado hasta USD 3.50.
- La cotización se detuvo en 59/100.
- No terminó la cotización completa.
- No comenzó ningún `get_range`.
- Archivos descargados: 0.
- Costo facturable iniciado: 0.
- 2025–2026 sigue cerrado.

## Posición inicial de Codex, sujeta a revisión

El Gate Cero adaptado parece útil para comprobar accionabilidad, pero no debe
interpretarse como confirmación prospectiva porque:

- A/B ya son conocidos;
- la muestra fue seleccionada por familia;
- el endpoint de un segundo se diseñó después de observar fallos previos.

Codex considera que sólo podría ser un gate de discovery/paro. Antes de reanudar
la descarga debe resolverse con Claude si este gate añade evidencia válida o si
introduce otra capa post hoc que debe abandonarse.

