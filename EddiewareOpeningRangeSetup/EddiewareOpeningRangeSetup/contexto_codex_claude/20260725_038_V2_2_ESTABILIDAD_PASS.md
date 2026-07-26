# V2-2 — Extracción, gate sintético y estabilidad: PASS

Fecha: 2026-07-25
Fase: V2-2/V2-3/V2-4 del handoff. Ejecutor: Claude Fable.
Estado información: `V2_STABILITY_NO_OUTCOME` (outcomes/mapping NO abiertos).

## 1. Qué se hizo

Implementado el extractor mecánico congelado del preregistro convergente
(`V2_PREREGISTRO_CONVERGENTE.md`, hash `22f9cadf098b1625...`), base normativa
`CODEX_V2_PROPOSAL.md`. Código sellado por hash ANTES de tocar los 98 casos
(`V2_CODE_HASHES.sha256`). Semántica de libro/paquetes copiada del pipeline
auditado congelado (`human_blind_v1_pipeline.py`): F_LAST atómico, A/M/C/R,
`aligned_trade`, orientación canónica por sigma.

13 componentes en 3 pilares:
- K cinemática (K1 ocupación, K2 terminal, K3 área, K4 latencia durable,
  K5 hold terminal, K6 coherencia cruces);
- B libro defensor (B1 fill/Q0, B2 refill 100 ms, B3 cesión cancels−adds,
  B4 supervivencia de cola, B5 migración profundidad);
- F tape (F1 imbalance, F2 persistencia).

## 2. Gate sintético A1 + MIRROR (antes de datos reales)

| Chequeo | Resultado |
|---|---|
| Orden `S(breakout) > S(ruido) > S(absorción)` | 10/10 PASS |
| Banda `absorción<−0.15 y breakout>+0.15` | ≥8/10 PASS |
| MIRROR BUY↔SELL exacto | ΔS=0, ΔQ=0 PASS |
| **GATE_A1** | **PASS** |

Ejemplo: breakout 0.754 / ruido 0.147 / absorción −0.628.

## 3. Cobertura sobre discovery

- 69/69 casos discovery evaluables (gate ≥56): **PASS**.
- Hard-fails: 0.

## 4. Puerta de estabilidad outcome-blind (P1:P5 + MIRROR)

Escalas `s_j` calculadas SOLO de inputs discovery 2022–2023, congeladas y
reutilizadas en todas las perturbaciones (`V2_SCALES.json`).

| Pert | Spearman | p95 \|ΔS\| | mediana \|ΔS\| | flips fuertes | retención | p95 \|ΔQ\| | PASS |
|---|---:|---:|---:|---:|---:|---:|:--:|
| P1 (tiempo 1 ms) | 0.9990 | 0.012 | 0.001 | 0 | 1.00 | 0.000 | ✅ |
| P2 (grid 10 ms) | 0.9981 | 0.037 | 0.003 | 0 | 1.00 | 0.000 | ✅ |
| P3 (grid +5 ms) | 0.9979 | 0.043 | 0.003 | 0 | 1.00 | 0.000 | ✅ |
| P4 (transport shuffle) | 1.0000 | 0.000 | 0.000 | 0 | 1.00 | 0.000 | ✅ |
| P5 (redondeo) | 1.0000 | 0.000 | 0.000 | 0 | 1.00 | 0.000 | ✅ |
| MIRROR | ΔS=0 | — | — | — | — | ΔQ=0 | ✅ |

Umbrales congelados: Spearman ≥0.98, p95 ≤0.15, mediana ≤0.05, flips ≤1 y ≤2%,
retención ≥95%, ΔQ ≤0.05. **JOINT_STABILITY = PASS.**

Nota P4: primera corrida FAIL (Spearman 0.954) por bug de reagrupación (ordené
solo por `sequence`). Corregido a round-trip fiel por identidad de paquete
(spec: "reagrupación por paquete, secuencia y F_LAST"); reejecutado → exacto.

## 5. Distribución del score en discovery (diagnóstico, sin outcomes)

- S ∈ [−0.556, +0.567], mediana −0.047; p25 −0.333, p75 +0.191.
- Banda neutra |S|≤0.15: 20/69. Aceptación S>0.15: 21. Defensa S<−0.15: 28.
- Simetría por lado: BUY media −0.049 (n=32), SELL −0.053 (n=37). Sin sesgo.

Score continuo real y balanceado, no colapsado a una clase. La incertidumbre
vive como magnitud (banda), no como clase C.

## 6. Integridad causal

- MFE/MAE/TP/SL/PnL: no leídos.
- Mapping / admin_sealed: no abiertos.
- Etiquetas AMD: no usadas.
- Endpoint / 2024 / 2025-26: no abiertos.
- Datos nuevos / ATAS: no.

## 7. Hashes

| Artefacto | SHA-256 |
|---|---|
| V2_STABILITY_RESULT.json | `c969b6d79dffe4482c77b352e6691e94251d94814e91ea3cf63c6f930cd1b6a4` |
| V2_SCALES.json | `fddd3a9ac6e6cb4f53081aad1eb1491845fbda420863d81027666b659ee82baf` |
| V2_SCORES_P0_98.csv | `da88216b95a1dd1feed2ea82eb6beb98a35b3c3817413d6d88f3d55bff1f4bdb` |
| v2_extractor.py | `d9087438b14f81c905d51e2cc605112165e7b6354a24748514f8fb53be88f0d1` |

## 8. Veredicto y siguiente paso

**V2-2/3/4 PASS.** El score mecánico es estable outcome-blind. Se autoriza —según
el preregistro— abrir discovery 2022–2023 UNA sola vez (Fase V2-5).

**Paso siguiente (IRREVERSIBLE, requiere OK del usuario):** abrir el único
endpoint continuo `rho_Spearman(S, Y_60)` sobre los 69 discovery. `Y_60` =
desplazamiento de midpoint a +60 s normalizado por OR (esto lee precio posterior
a la ventana de 5 s por primera vez). Éxito congelado: `rho_hat ≥ 0.25 AND
IC95_low > 0`, bootstrap por sesión 10,000, seed `0x22f9cadf098b1625`. Sin
segundo intento, sin endpoint alternativo. 2024 solo confirmatorio después.

`INFORMATION_STATUS=V2_STABILITY_PASS_NO_OUTCOME`
