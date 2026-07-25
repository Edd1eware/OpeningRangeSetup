# Ronda 005 — dictamen preflight

## 1. Inicio 08:29 CT: ACEPTADO

- Aritmética verificada: con `t_decision >= 08:31:00` (bursts post-OR), el tramo 08:29:00→`t_decision`−60 s garantiza ≥12 ventanas de 5 s por sesión en grid determinista. Soporte por sesión queda cumplido por construcción, sin excluir las 33 sesiones ni seleccionar por latencia del burst — la alternativa (exclusión) sesgaba peor.
- La enmienda usa solo disponibilidad temporal del manifiesto, sin trayectorias ni outcomes: label-blind, admisible antes de resultados. Debe asentarse en el registro de desviaciones como enmienda pre-resultado.
- Sesgo conocido a registrar, no fatal: 08:29–08:30 es pre-apertura de cash; vol algo menor que 08:31+ → percentiles T ligeramente bajos → tendencia a más etiquetas A/B. El gate de prevalencia bilateral 15%–70% ya lo contiene. Diagnóstico no vinculante: reportar percentiles con y sin el minuto 08:29, sin que altere el veredicto.

## 2. Orientación dual determinista y dwell continuo: ACEPTADOS

- Dual `s=±1` elimina RNG de dirección; correcto contar soporte por ventanas físicas, no por orientaciones correlacionadas.
- Dwell continuo post-cruce con muerte del intento al abandonar el umbral, y reintento por cruce posterior: es la lectura correcta y más estricta de mi fórmula 004; determinista y sin ambigüedad.
- `ts_event` empatado por `sequence` con dwell cero intratimestamp: idéntico a 004.

## 3. Defecto fatal

No detecto defecto causal ni estadístico fatal. Ninguna trayectoria, desplazamiento ni etiqueta fue observada; fórmulas, umbrales, ventana objetivo y gates predictivos quedan intactos; el cambio es de disponibilidad de soporte, decidido a ciegas. Únicos puntos no fatales ya asentados: mezcla de régimen 08:29 (con dirección de sesgo conocida y gate que la contiene) y ventanas que tocan el spike de 08:30:00 en sesiones tardías (efecto conservador: infla T_ext, dificulta B).

Secuencia vigente sin cambios: congelar V2 con hash → gates de soporte y sensibilidad → cotizar tape 5.1 s ×98 → autorización del usuario → descargar → etiquetar → contraste predictivo. Revisión única: consumida; tras este congelamiento, ningún cambio más.

`CONVERGENCIA_FINAL_V2`
