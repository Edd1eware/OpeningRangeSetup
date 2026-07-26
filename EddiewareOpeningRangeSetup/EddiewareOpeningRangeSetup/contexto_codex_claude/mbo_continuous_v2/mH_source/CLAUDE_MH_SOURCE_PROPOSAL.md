# Propuesta Claude — fuente de mH para el endpoint Y_60 (addendum V2-5)

Fecha: 2026-07-25
Autor: Claude Fable (sellada por hash antes de ver la de Codex)
Contexto: doc `20260725_039_V2_5_BLOQUEO_HORIZONTE_ENDPOINT.md`. El endpoint Y_60
congelado necesita `mH` (midpoint en cutoff+65 s), ausente en datos sellados.
Usuario autorizó descarga acotada (opción 1). El endpoint `Y_60` NO cambia; solo
se preregistra la fuente de `mH`.

## 1. Qué se descarga (mínimo necesario)

- Producto: **MBP-1** (top-of-book) Databento, dataset `GLBX.MDP3`. Misma fuente
  y reloj que el MBO sellado; MBP-1 da best_bid/best_ask → midpoint directo.
- Símbolo: `resolved_raw_symbol` por evento (contrato NQ front ya resuelto y
  sellado en `DATABENTO_MBO_SNAPSHOT_DISCOVERY_100_RESOLVED_20260723.csv`),
  `stype_in=raw_symbol`.
- Ventana por evento: `[cutoff + 64.000 s, cutoff + 65.050 s)` por `ts_recv`
  (≈1.05 s). Suficiente para hallar el último BBO ≤ +65 s con antigüedad ≤1 s en
  NQ líquido a las ~09:31–09:35 ET. NADA fuera de esa ventana.
- 98 eventos. Sin padding adicional.

## 2. Cómo se calcula mH y Y_60 (endpoint sin cambios)

```text
m1 = midpoint del último BBO completo con ts_recv < t1, tomado del OUTCOME DBN
     YA SELLADO (disponible a +5 s). Fuente: MBO sellado.
mH = midpoint del último BBO completo con ts_recv <= t1+60s = cutoff+65s,
     antigüedad máxima 1.000 s, tomado de la nueva MBP-1.
     Si no hay BBO válido en (cutoff+64s, cutoff+65s] con antigüedad <=1s -> mH ausente.
OR_ticks = (OR_high-OR_low)/delta_p, OR íntegro anterior a t0 (ya congelado).
Y_60 = sigma * [(mH - m1)/delta_p] / max(OR_ticks, 1)
```

- `m1` sigue saliendo del MBO sellado (no se redescarga). `mH` de la nueva MBP-1.
- Ambos midpoints son (best_bid+best_ask)/2 de Databento GLBX. No se mezclan
  proveedores ni relojes distintos.
- Faltantes: si `mH` ausente para un caso, ese caso no entra al endpoint. Regla de
  cobertura del endpoint intacta: se requieren ≥56 pares válidos `(S,Y_60)`; si
  <56, discovery = FAIL_COVERAGE.

## 3. Integridad y límites

- Solo se descarga la ventana de 1.05 s alrededor de +65 s. No se abre nada entre
  +5 s y +64 s (no se usa el camino intermedio, solo el punto terminal +65 s).
- Costo estimado por `metadata.get_cost` (gratis) ANTES de descargar; se reporta y
  se respeta un tope. Recibo con SHA-256 de cada archivo.
- El disparo único discovery se ejecuta UNA vez después de tener `Y_60`.
- Prohibido seguir descargando, cambiar horizonte (+60 s fijo), o mezclar
  productos distintos a MBP-1/MBO de GLBX.

## 4. Orden

1. Codex converge sobre esta fuente → addendum hasheado.
2. `metadata.get_cost` de los 98 → reportar total al usuario.
3. Descargar MBP-1 (98 ventanas), recibo SHA-256.
4. Construir `Y_60`, verificar cobertura ≥56.
5. Ejecutar endpoint único `rho_Spearman(S, Y_60)`, bootstrap 10k, seed
   `0x22f9cadf098b1625`, IC95. Éxito `rho_hat≥0.25 AND IC95_low>0`.
