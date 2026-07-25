# Convergencia V2 — preregistro firmado por Claude + Codex

Fecha: 2026-07-25
Estado: **CONVERGENCIA FINAL V2-1 — PREREGISTRO SELLADO**

## Protocolo ejecutado

1. V2-0 PASS (doc 035): 15/15 hashes, sellados admin intactos.
2. Claude escribió propuesta y la selló por hash ANTES de contactar a Codex (doc 036).
3. Claude lanzó a Codex vía CLI (`codex exec`, modelo gpt-5.6-sol) con prohibición
   de leer `claude_sealed`. Codex entregó propuesta independiente sellada
   (`CLAUDE_PROPOSAL_UNREAD` verificado; sello Claude intacto post-entrega).
4. Claude abrió ambas, redactó `V2_PREREGISTRO_CONVERGENTE.md`.
5. Codex revisó y contrafirmó: **FIRMADO**, 3 observaciones editoriales no
   bloqueantes (`CODEX_COUNTERSIGN.md`).

## Hashes sellados

| Artefacto | SHA-256 |
|---|---|
| `claude_sealed\CLAUDE_V2_PROPOSAL.md` | `67a6d306389c8332128f6f089303ad9204882ba5ec1c38d0ea6a39f7a5e395cc` |
| `codex_sealed\CODEX_V2_PROPOSAL.md` | `9131b8ad7e586c0dcf991a7d75050624c038903acf55360c8eee52b4cd19e8ea` |
| `V2_PREREGISTRO_CONVERGENTE.md` | `22f9cadf098b1625a89046ed5bfbe8f27cace3f29f05f8b78105a841b4094f9a` |
| `CODEX_COUNTERSIGN.md` | `056af71dcf37cbb4637e3b3fd4f1debd94f1112684e9ea6af974890d32afd1c9` |

**Seed bootstrap congelado** (primeros 64 bits del hash del preregistro):
`0x22f9cadf098b1625`

## Especificación congelada (resumen)

- 13 componentes causales en 3 pilares: K cinemática (6), B libro defensor (5),
  F tape (2); pesos 1/3 por pilar, iguales dentro.
- Normalización `tanh(r/s_j)`, floors congelados, sin centrado, escalas SOLO de
  inputs discovery 2022–2023.
- `S_defensa_aceptacion ∈ [-1,1]` (aceptación +, defensa −); `Q_cobertura` separada;
  banda neutra fija `±0.15` (tolerancia, no clase).
- Cobertura: caso evaluable requiere `Q≥0.90` y bloques `≥0.80`; discovery necesita
  ≥56/69 evaluables.
- Enmienda A1: gate sintético de ordenamiento (breakout > ruido > absorción 10/10)
  + espejo BUY/SELL 1e-12, antes de estabilidad.
- Estabilidad: P1:P5 deterministas; Spearman ≥0.98, medianΔ ≤0.05, p95 ≤0.15,
  flip fuerte ≤1 caso y ≤2%, retención ≥95%, ΔQ ≤0.05. Un fallo = no abrir outcomes.
- Endpoint único: `rho_Spearman(S, Y_60)`; `Y_60` = desplazamiento midpoint a +60 s
  normalizado por OR, orientado. Éxito: `rho_hat ≥ 0.25 AND IC95_low > 0`
  (bootstrap por sesión, 10,000, seed congelado).
- 2024: una sola apertura confirmatoria si discovery PASS exacto (7 condiciones);
  enmienda A2 publica rho por lado BUY/SELL como evidencia secundaria.
- 2025–2026 cerrado.

## Integridad causal

- Mapping/outcomes/admin_sealed: NO abiertos por ninguno de los dos agentes.
- MFE/MAE/TP/SL/PnL: no usados.
- Etiquetas AMD: no usadas como target.
- Datos nuevos/ATAS: no.

## Next steps (V2-2)

1. Implementar extractor de los 13 componentes desde MBO snapshot (código hasheado
   antes de correr sobre los 98 casos).
2. Generador de secuencias sintéticas + gate A1 + MIRROR.
3. Escalas `s_j` desde discovery → hashear.
4. P0 + P1:P5 → gate conjunto de estabilidad.
5. Solo si PASS: única apertura discovery.

`INFORMATION_STATUS=V2_PREREG_SIGNED_NO_OUTCOME`
