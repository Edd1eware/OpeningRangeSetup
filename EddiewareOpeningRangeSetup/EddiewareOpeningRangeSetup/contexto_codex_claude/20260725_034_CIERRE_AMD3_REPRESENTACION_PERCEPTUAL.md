# Cierre AMD-3 — Representación perceptual A/B/C

Fecha: 2026-07-25  
Objetivo: distinguir absorción limpia de breakout limpio causalmente después del Liquidity Burst.

## Veredicto

**NO SOY CAPAZ DE SEPARAR DE FORMA ESTABLE UNA ABSORCIÓN LIMPIA DE UN BREAKOUT LIMPIO CON ESTA REPRESENTACIÓN PERCEPTUAL CATEGÓRICA.**

La dirección A frente a B fue consistente cuando ambos codificadores se comprometieron con una clase, pero la frontera que decide cuándo abstenerse como C no fue reproducible bajo cambios cosméticos.

## Historial completo

### AMD-1 — Panel humano + IA

- Eduardo–Claude–Codex alpha nominal: 0.4396.
- Gate: >=0.60.
- Resultado: FAIL.

Las etiquetas humanas se conservaron como auditoría y fueron excluidas operativamente por instrucción del usuario.

### AMD-2 — Consenso Claude–Codex

Antes de outcome:

- acuerdo Claude–Codex: 82/98 = 83.67%;
- Cohen kappa: 0.7538;
- alpha nominal: 0.7546;
- regla A/A→A, B/B→B, todo lo demás→C;
- distribución A=27, B=35, C=36.

Primera perturbación cosmética:

- denominador original A/B: 62;
- flips: 9;
- flip rate: 14.516%;
- gate: <=10%;
- resultado: FAIL.

Transiciones:

- A→A 20;
- A→C 7;
- B→B 33;
- B→C 2;
- C→A 7;
- C→C 29;
- A↔B 0.

### AMD-3 — Stable Core

Núcleo estable construido sin outcome:

- A=20;
- B=33;
- C=45;
- denominador A/B=53.

Segunda perturbación cosmética independiente:

- flips: 7/53;
- flip rate: 13.208%;
- gate: <=10%;
- resultado: FAIL.

Transiciones:

- A→A 13;
- A→C 7;
- B→B 33;
- C→A 5;
- C→B 3;
- C→C 37;
- A↔B 0.

## Qué demuestra

1. Claude y Codex comparten una lectura direccional A/B consistente.
2. En dos perturbaciones no apareció ninguna inversión A↔B.
3. El problema está concentrado en la frontera C/abstención.
4. La paleta y presentación cosmética cambian qué casos reciben suficiente confianza para ser A/B.
5. Una clasificación dura A/B/C basada en este renderer no cumple el estándar de estabilidad preregistrado.

## Qué no demuestra

- No demuestra que la dirección IA prediga MFE/OR.
- No demuestra que las etiquetas sean correctas.
- No demuestra separación económica ni mejora de WR/PF.
- No autoriza a reinterpretar los FAIL eliminando C del endpoint.

## Integridad

- Mapping abierto: no.
- Outcomes abiertos: no.
- MFE, MAE, TP, SL o PnL usados: no.
- Discovery 2022–2023 ejecutado: no.
- Validation 2024: cerrada.
- 2025–2026: cerrado.

## Hallazgo aprovechable

La ausencia total de flips direccionales sugiere que la información útil no debería expresarse como una clase perceptual dura con una frontera C subjetiva. El siguiente diseño debe medir un **score causal continuo de defensa versus aceptación**, dejando la incertidumbre como magnitud del score y no como una tercera clase elegida visualmente.

## Next steps propuestos

1. Cerrar nuevas recodificaciones cosméticas sobre estos 98 casos; repetirlas sería un forking path.
2. Diseñar Claude–Codex V2 como score mecánico continuo, calculado directamente de MBO entre cutoff y +5 s.
3. Componentes candidatos, todos causales:
   - proporción del tiempo con aceptación más allá de L0;
   - desplazamiento terminal y área firmada del BBO;
   - número y momento de reclaims de L0;
   - fill pasivo/Q0;
   - refill posterior a fill;
   - adds menos cancels bajo agresión;
   - supervivencia de cola ponderada por agresión;
   - migración del libro y tape alineado frente a counterflow.
4. Congelar orientación, normalización, pesos y un único endpoint de estabilidad antes de mirar outcomes.
5. Calibrar únicamente con casos sintéticos o nuevas ventanas outcome-blind, no corrigiendo contra estos resultados.
6. Si el score V2 es estable, ejecutar una sola prueba discovery; 2024 seguirá siendo la única validación confirmatoria.

## Artefactos

- `human_blind_v1/amd2_stability/audit/AMD2_STABILITY_RESULT.json`
- `human_blind_v1/amd3_stability/audit/AMD3_STABILITY_RESULT.json`
- `human_blind_v1/amd3_stability/audit/AMD3_STABILITY_CASES_98.csv`
- `human_blind_v1/amd3_stability/audit/AMD3_RESULT_HASHES.sha256`

`INFORMATION_STATUS=PERCEPTUAL_REPRESENTATION_CLOSED_NO_OUTCOME`
