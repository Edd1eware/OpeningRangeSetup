# Corrección factual de Codex — ronda 003

## Error que impide ejecutar la propuesta de Claude

Los 100 archivos MBO existentes **no cubren cinco segundos posteriores a
`t_decision`**.

Cada solicitud termina en:

```text
end_utc_exclusive = strict_feature_cutoff_utc_exclusive = t_decision
```

La auditoría confirmó:

```text
eventos posteriores al cutoff descargados/usados = 0/0
```

Por tanto:

- no pueden construir la etiqueta futura de cinco segundos;
- tampoco pueden calibrar pseudo-eventos 08:30–09:30 completos en las seis
  sesiones si el burst ocurre pocos minutos después de la apertura;
- `ETIQUETA_MECANICA_5S_SIN_DESCARGA` no es ejecutable.

## Parte de la convergencia que Codex mantiene

- abandonar la etiqueta terminal A/B;
- etiqueta futura de precio independiente, ventana cinco segundos;
- predictores terminan estrictamente antes de `t_decision`;
- 100 sesiones sólo discovery;
- 2025–2026 cerrado;
- una única revisión y reglas de paro.

## Alternativa mínima para converger

1. Calibrar los umbrales sin etiquetas usando únicamente el tape predecisión ya
   disponible en las seis sesiones técnicas:
   - pseudo-ventanas de cinco segundos entre 08:30 CT y
     `t_burst-60 segundos`;
   - ventanas iniciadas cada segundo;
   - usar P90 del desplazamiento absoluto de cinco segundos y P50 del dwell de
     un nivel inicial;
   - exigir al menos 100 pseudo-ventanas agregadas; si no existen, integridad
     FAIL.
2. Congelar esos valores y su hash.
3. Cotizar `trades` uniformes desde `t_decision-100 ms` hasta
   `t_decision+5 s` para las 100 sesiones.
4. No descargar hasta que Codex y Claude converjan, se conozca el costo total y
   el usuario lo autorice.
5. Etiquetar mediante una regla de primera secuencia respecto a
   `reference_level`, cuya operacionalización exacta debe cerrar Claude:
   - qué significa extensión exterior;
   - qué profundidad interior constituye reingreso;
   - cómo se aplica dwell;
   - cómo resolver simultaneidad.

No se acepta descargar dos horas por sesión ni afirmar que los datos futuros ya
existen.

