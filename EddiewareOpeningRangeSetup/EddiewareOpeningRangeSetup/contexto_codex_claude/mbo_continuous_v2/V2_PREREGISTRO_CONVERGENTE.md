# V2 — Preregistro convergente Claude + Codex (score mecánico continuo)

Fecha: 2026-07-25
Estado: CONVERGENTE — pendiente contrafirma Codex; se hashea al firmar.
Fase: cierre de V2-1 del handoff `HANDOFF_LIQUIDITY_BURST_MBO_V2_NEXT_STEPS_20260725.md`.

## 1. Protocolo de independencia cumplido

| Propuesta | Archivo | SHA-256 | Sellada antes de ver la otra |
|---|---|---|---|
| Claude | `claude_sealed\CLAUDE_V2_PROPOSAL.md` | `67a6d306389c8332128f6f089303ad9204882ba5ec1c38d0ea6a39f7a5e395cc` | Sí (hash publicado en doc 036 antes de lanzar Codex) |
| Codex | `codex_sealed\CODEX_V2_PROPOSAL.md` | `9131b8ad7e586c0dcf991a7d75050624c038903acf55360c8eee52b4cd19e8ea` | Sí (`CLAUDE_PROPOSAL_UNREAD`, verificado) |

Ambos hashes verificados post-entrega: intactos.

## 2. Especificación normativa

**La especificación base es la propuesta Codex íntegra** (`CODEX_V2_PROPOSAL.md`,
hash arriba): secciones 0–10 con sus 13 componentes en tres pilares (K cinemática,
B libro defensor, F tape), orientación sigma, normalización `tanh(r/s_j)` con
floors congelados y sin centrado, regla `F_LAST` atómica, score
`S=(S_K+S_B+S_F)/3`, `Q_cobertura` por bloque, banda neutra `±0.15`,
perturbaciones `P1:P5+MIRROR` con sus seis gates, endpoint único
`rho_Spearman(S, Y_60)` con éxito `rho_hat>=0.25 AND IC95_low>0`, y los siete
puntos auditables para abrir 2024.

Se adopta como base por ser un superconjunto compatible de la propuesta Claude con
definiciones más precisas. Divergencias resueltas en la tabla de la sección 4.

## 3. Enmiendas convergentes (parte normativa junto con la base)

**A1 — Gate sintético de ordenamiento (previo a estabilidad).**
Antes de ejecutar `P1:P5` sobre datos reales: generar 10 secuencias sintéticas
deterministas por tipo — absorción pura (fills sin desplazamiento, refill alto,
cola sobrevive), breakout puro (depleción, desplazamiento sostenido, migración),
ruido plano (sin fills netos ni desplazamiento). Gate:
`S(breakout) > S(ruido) > S(absorción)` en 10/10 tripletes, y
`S(absorción) < -0.15 < +0.15 < S(breakout)` en al menos 8/10.
FAIL → bug de implementación; se corrige código, no la especificación. Las
secuencias sintéticas se generan antes de tocar los 98 casos reales y se hashean.

**A2 — Consistencia por lado en 2024 (gate secundario).**
Al abrir 2024, además del endpoint primario congelado, se calcula y reporta
`rho_Spearman(S, Y_60)` por lado BUY y SELL. El veredicto VALIDADO/NO VALIDADO lo
decide únicamente el endpoint primario; el signo por lado se publica como evidencia
secundaria obligatoria (no se oculta si contradice).

**A3 — Seed.**
Seed del bootstrap = primeros 64 bits del SHA-256 de este preregistro firmado
(regla Codex, aplica también al bootstrap de 2024).

## 4. Divergencias entre propuestas y resolución

| Tema | Claude proponía | Codex proponía | Resolución |
|---|---|---|---|
| Componentes | 8 planos | 13 en 3 pilares (añade K4 latencia, K6 cruces, B4 supervivencia id, B5 migración) | Codex: pilares evitan sobre-peso del libro; B4/B5 cubiertos por gate sintético A1 |
| Normalización | z robusto mediana/MAD ±3 | `tanh(r/p75)` sin centrar, floors | Codex: preservar cero mecánico es correcto para score firmado |
| Fuente de escalas | pseudoventanas predecisión | inputs de las 69 ventanas discovery | Codex; pseudoventanas quedan solo para pruebas de software |
| Banda neutra | p25 de \|S\| en pseudoventanas | fija `±0.15` | Codex: congelable sin dependencia distribucional |
| Gates estabilidad | Spearman ≥0.90, flips ≤5% | Spearman ≥0.98, medianΔ ≤0.05, p95 ≤0.15, flip fuerte ≤1 y ≤2%, retención ≥95%, ΔQ ≤0.05, MIRROR 1e-12 | Codex (estrictamente más duro; ambos aceptan) |
| Endpoint outcome | `D_norm` horizonte abierto, ρ≥0.35 | `Y_60` midpoint +60s / OR, ρ≥0.25 + IC95_low>0 | Codex define horizonte y outcome no-MFE; umbral 0.25 aceptado porque `IC95_low>0` con n≥56 ya controla azar y 0.25 es el piso de efecto; Claude cede 0.35 y queda registrado |
| Calibración sintética | orden 10/10 por tipo | solo MIRROR | Ambos: A1 + MIRROR |
| 2024 por lado | mismo signo ρ BUY/SELL | no incluido | A2 como gate secundario reportado |
| Cobertura mínima | Q≥0.75, 6/8 comp | Q≥0.90, bloques ≥0.80, 56/69 casos | Codex (más duro) |

Ninguna resolución usó outcomes, etiquetas AMD ni mapping: convergencia 100%
outcome-blind.

## 5. Orden de ejecución congelado

```text
1. Contrafirma Codex de este preregistro → hash SHA-256 publicado
2. Implementar extractor (código hasheado antes de correr sobre los 98)
3. Gate sintético A1 + MIRROR
4. Escalas s_j desde inputs discovery 2022–2023 (outcome-blind) → hasheadas
5. P0 + P1:P5 sobre discovery → gate conjunto estabilidad
6. FAIL → V2_STABILITY_FAIL, no abrir outcomes, documentar
7. PASS → única apertura discovery 2022–2023 (endpoint sección 9 base)
8. PASS exacto → única apertura 2024 (sección 10 base + A2)
9. 2025–2026 permanece cerrado
```

## 6. Prohibiciones vigentes

Sin MFE/MAE/TP/SL/PnL en diseño; sin etiquetas AMD como target; sin abrir
mapping/`admin_sealed`; sin descargar datos; sin ATAS; sin endpoint alternativo;
sin segunda apertura; sin cambio post-firma de fórmula, escalas, gates, horizonte
o seed.

Firmas:
- Claude Fable: FIRMADO 2026-07-25.
- Codex: PENDIENTE (contrafirma en `CODEX_COUNTERSIGN.md`).
