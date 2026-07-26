# Errata H2-001 — corrección de defecto de implementación (append-only)

Fecha: 2026-07-25

## Qué pasó

La primera ejecución de H2 seleccionó **0 trades** en FRESH. Eso no es un
resultado de la hipótesis: es un defecto de implementación que impidió que la
prueba se ejecutara.

## Causa raíz

```text
rng_60 == 0 en 154 de 698 sesiones  ->  |net_60|/rng_60 = NaN en esas 154
rolling(20, min_periods=20) exige 20 observaciones NO-NaN consecutivas
con 154 NaN dispersos, ninguna ventana de 20 queda completa
resultado: trendiness = NaN en las 698 sesiones -> umbral DEV = NaN
           -> regime_ok = False siempre -> seleccion vacia
```

## Corrección

El preregistro dice literalmente: *"media sobre las K sesiones PREVIAS de
`|net_60| / rng_60`"*. No exige que las 20 estén definidas. Se corrige a:

```text
min_periods = 10      (al menos la mitad de la ventana con dato valido)
```

La media sigue siendo sobre las 20 sesiones previas con `shift(1)` (causal, hoy
excluido); simplemente se calcula sobre las observaciones válidas dentro de esa
ventana. K sigue siendo 20 y el umbral sigue siendo la mediana de DEV. **No se
cambia ningún otro elemento** del preregistro.

## Integridad

- El único "resultado" previo era `n=0`, que no contiene información alguna sobre
  la hipótesis. No hubo oportunidad de ver desempeño y ajustar en consecuencia.
- La corrección se decide **antes** de observar cualquier métrica de H2.
- `min_periods=10` es una elección única y convencional (mitad de ventana). No se
  barre ni se prueba otro valor.
- Esta errata es append-only: no se edita el preregistro original.

`INFORMATION_STATUS=H2_ERRATA_BEFORE_RESULT`
