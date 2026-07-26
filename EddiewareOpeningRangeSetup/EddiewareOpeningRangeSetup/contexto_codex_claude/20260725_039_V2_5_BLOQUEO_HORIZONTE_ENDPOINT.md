# V2-5 — Bloqueo de horizonte del endpoint (Y_60 no existe en datos sellados)

Fecha: 2026-07-25
Fase: V2-5 (apertura discovery). Ejecutor: Claude Fable.
Estado información: `NO_OUTCOME_OPENED` (single-shot discovery INTACTO).

## 1. Autorización y verificación previa

El usuario autorizó abrir el endpoint discovery. Antes de abrirlo, verifiqué la
cobertura temporal de los datos sellados requerida por el endpoint congelado:

```text
Y_60 = sigma * [(mH - m1)/delta_p] / max(OR_ticks,1)
  m1 = midpoint del último BBO completo anterior a t1  (t1 = cutoff + 5s)
  mH = midpoint del último BBO completo en/antes de t1 + 60s = cutoff + 65s
```

## 2. Hallazgo: el horizonte +60 s no está en ningún dato sellado

| Fuente sellada | Cobertura temporal (rel. cutoff) | Aporta mH (+65 s)? |
|---|---|---|
| `joint_ab_v4_outcome98` (outcome DBN) | [−0.1 s, +5.1 s] | NO |
| `snapshot_discovery100` (pre-historia) | [−48 721 s, 0 s] | NO |

Verificado en casos BUY 2022, SELL 2023, SELL 2024. El único dato post-cutoff
llega a +5.1 s. `m1` (en t1=+5 s) SÍ existe; `mH` (en +65 s) NO existe en
ninguna parte del MBO Databento sellado.

## 3. Por qué es un bloqueo duro (no lo resuelvo solo)

El preregistro convergente prohíbe explícitamente:
- descargar más MBO;
- sustituir el horizonte del endpoint;
- mezclar proveedores/relojes (p. ej. usar `ohlcv-1s-full` de otro producto).

Además, el único dato post-cutoff disponible (+5 s) coincide con la ventana de
features → cualquier "outcome" in-window sería circular con el score (K2 ya es
el desplazamiento terminal a +5 s). **No existe un outcome fuera de muestra en
los datos sellados.**

## 4. Integridad preservada

- Outcomes abiertos: NO. Solo se inspeccionaron rangos de `ts_recv` y conteos de
  filas (metadatos de ventana), nunca precio futuro ni MFE/MAE/PnL.
- El disparo único de discovery sigue INTACTO.
- Fórmula, escalas, código y gate de estabilidad permanecen congelados y válidos
  (`20260725_038_V2_2_ESTABILIDAD_PASS.md`, JOINT_STABILITY PASS).

## 5. Opciones (requieren convergencia Claude+Codex y decisión del usuario)

| # | Opción | Costo | Viabilidad |
|---|---|---|---|
| 1 | Descargar MBO/MBP-1 post-decisión (~+65 s) para los 98 eventos sellados; mantener Y_60 tal cual; re-preregistrar solo la fuente | $ nueva descarga (acotada; midpoint en 1 instante ≈ MBP-1 barato) | **Recomendada** — limpia, misma fuente, endpoint sin cambios |
| 2 | Re-preregistrar el endpoint a un horizonte que exista en datos sellados | $0 | **Inviable** — único post-dato es +5 s, circular con features |
| 3 | Cerrar V2 como "score estable pero NO validado contra futuro" | $0 | Válido pero deja el edge sin confirmar |

## 6. Recomendación

Opción 1: descarga acotada de top-of-book (MBP-1) alrededor de +65 s para los 98
eventos ya sellados, misma fuente Databento, endpoint `Y_60` sin cambios. Antes:
Claude+Codex convergen y re-preregistran únicamente la fuente de `mH`
(hasheado), el usuario autoriza el gasto. El disparo discovery se ejecuta una
sola vez después.

**NO se descarga, NO se abre outcome y NO se sustituye horizonte sin esa
convergencia + autorización.**

`INFORMATION_STATUS=V2_5_BLOCKED_HORIZON_NO_OUTCOME`
