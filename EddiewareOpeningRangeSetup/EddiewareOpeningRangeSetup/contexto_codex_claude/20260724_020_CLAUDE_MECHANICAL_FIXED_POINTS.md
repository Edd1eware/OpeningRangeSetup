# Claude/Fable — etiqueta mecánica por puntos fijos

## Frontera causal

- Reloj: `ts_recv`.
- Estado inicial: libro confirmado al `strict_feature_cutoff`.
- Ventana: `[cutoff, cutoff+5s)`.
- Paquetes aplicados atómicamente sólo al recibir `F_LAST`.
- Registros con `ts_event<cutoff` pero `ts_recv>=cutoff` son información
  futura.
- BUY ataca ask L0; SELL ataca bid L0.

## Etiqueta

```text
L0    = mejor ask (BUY) o mejor bid (SELL) en cutoff
Q0    = tamaño visible en L0 en cutoff
F_dep = fills explícitos contra L0
C_dep = cancelación pura en L0, sin F hermana en el Match Event
Q_end = tamaño visible en L0 al final
cedido(t) = BUY: best_ask > L0; SELL: best_bid < L0
```

A absorción limpia:

```text
F_dep >= 0.5 * Q0
y nunca cedido durante W
y Q_end > 0
```

B breakout limpio:

```text
Q(L0) llega a cero
y F_dep/(F_dep+C_dep) >= 0.5
y cedido al final de W
```

C: retiro puro, vacío con recuperación, agresión insuficiente, plano o resto.

## Gates

- Sensibilidad de ambos 0.5 a 0.425/0.575: Jaccard A/B >=0.70.
- A>=15%, B>=15%, ninguna clase limpia >70%.
- A/B por año y BUY/SELL.
- Aplicación única; cualquier FAIL cierra la línea sin rescates.

`CONVERGENCIA_ETIQUETA_MECANICA_PUNTOS_FIJOS`
