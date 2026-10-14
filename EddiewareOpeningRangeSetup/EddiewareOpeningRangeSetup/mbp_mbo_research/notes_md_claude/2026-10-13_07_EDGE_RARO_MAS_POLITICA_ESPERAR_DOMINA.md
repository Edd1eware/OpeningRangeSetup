# 07 — Un edge raro bajo la política de tamaño: esperar domina

Fecha: 2026-10-13. Script: `43_combined_edge_and_policy.py`. Reporte: `combined_edge_policy.csv`.

## El choque que ninguna de las dos notas vio

Las dos mitades de la sesión no se combinan como cada una se lee por separado:

- **Nota 03**: la política taper pasa el 43% de las evaluaciones 50K con cero edge, **asumiendo un trade cada
  día**.
- **Nota 06**: el efecto turn of month, si es real, existe **unos tres días al mes**.

Una regla que dispara tres veces al mes no puede alimentar una política de un trade diario. O el trader espera,
y entonces la evaluación tarda meses en vez de días, o rellena los otros días con trades sin edge, que diluyen
el win rate hacia el volado mientras siguen pagando costo en cada uno.

## La medición

Mismo tamaño taper, mismo costo de 1.8 ticks, mismas reglas de la 50K. Lo único que cambia es con qué
frecuencia se apuesta y a qué win rate. 40,000 cuentas por celda, horizonte duro de 500 días hábiles.

| WR en días de edge | esperar (3 días/mes) | diario, relleno 0.50 | diario, relleno 0.48 |
|---|---:|---:|---:|
| 0.50 (sin edge) | **0.4328** en 35 días | 0.4310 en 5 días | 0.3997 |
| 0.53 | **0.4895** | 0.4359 | 0.4032 |
| 0.55 | **0.5258** | 0.4360 | 0.3987 |
| 0.57 | **0.5653** | 0.4386 | 0.3987 |
| 0.60 | **0.6209** | 0.4421 | 0.3993 |
| 0.65 | **0.7064** | 0.4416 | 0.4069 |

Tiempo del brazo que espera, cap $1,500: mediana **35 días naturales**, percentil 90 entre 70 y 91 días, y
**5 trades** de mediana para pasar.

## Las tres lecturas

**1. Operar diario está topado en ~44% por bueno que sea el edge.** De 0.50 a 0.65 en los días buenos, la
probabilidad sube de 0.4310 a 0.4416. Once centésimas de win rate en los días que importan se evaporan porque
dieciocho de veintiún días son volados que diluyen todo y cobran costo. El edge se ahoga en el relleno.

**2. El relleno realista es peor que un volado.** Todas las reglas que este proyecto probó salieron
ligeramente negativas después de costo, así que 0.48 es el número honesto para los días sin señal, no 0.50. Con
relleno a 0.48 el brazo diario cae a ~0.40 y **deja de mejorar con el edge por completo**: 0.3997 con WR 0.50
en los días buenos y 0.4069 con WR 0.65. Operar por operar destruye exactamente lo que la espera construye.

**3. Esperar sale gratis.** Con cero edge los dos brazos empatan, 0.4328 contra 0.4310. La mediana de trades
para pasar es 5 en los dos; lo único que cambia es el calendario. O sea que la política escasa **domina
débilmente siempre y domina fuerte en cuanto haya cualquier edge**, y el precio de equivocarse sobre el edge es
tiempo, no probabilidad.

Eso convierte la decisión en una que no depende de tener razón sobre el turn of month: aunque el candidato de
la nota 06 muera con los datos nuevos, esperar los días de calendario y no operar el resto sigue siendo al
menos tan bueno como operar diario, y mucho mejor si el relleno es levemente negativo, que es lo que la
evidencia de este proyecto dice que es.

## Lo que no está modelado

- Los trades se simulan independientes. Tres días consecutivos del mismo turn of month no lo son.
- El horizonte de 500 días hábiles es duro; una evaluación real no tiene límite de tiempo en Lucid, pero sí lo
  tiene la paciencia.
- El WR en días de edge sigue sin medirse sobre NQ con muestra suficiente. Toda la columna de la izquierda es
  condicional a un número que el script 41 producirá cuando termine la descarga.
