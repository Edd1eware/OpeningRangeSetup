# HUMAN BLIND V1 — Codificadores IA sellados

Fecha: 2026-07-24  
Enmienda vigente: HUMAN_BLIND_V1_AMD1

## Estado

- CODEX completó 98/98 casos en su propio orden aleatorio.
- CLAUDE completó 98/98 casos en un orden aleatorio diferente.
- Ambos archivos tienen 98 CaseID únicos, ordinales completos y únicamente etiquetas A/B/C.
- Los dos codificadores terminaron antes de comparar sus salidas.
- No se cargaron mapping, fechas, contrato, lado real, outcome, familia histórica, MFE, MAE, TP, SL ni PnL.
- No se entrenó ningún modelo.

## Rúbrica efectiva

El nombre real de la rúbrica congelada es:

`human_blind_v1/frozen/RUBRICA_PERCEPTUAL_V1.md`

El prompt de Claude citaba por error `RUBRICA_CIEGA_HUMANA_V1.md`, archivo que no existe. Claude detectó el nombre incorrecto y utilizó la única rúbrica perceptual congelada disponible. Esto quedó declarado expresamente en su recibo. Codex aplicó la misma definición A/B/C.

## Sellos SHA-256

### Codex

- `CODEX_LABELS_98.csv`: `413a82d472e3897de270698762a8f4a0675ce67a8102bb45790761611bb08e32`
- `CODEX_CODING_RECEIPT.md`: `69824c611cf8162a2c01d84a8dcdab50991b5c88402bd0fbea23c31e16ab45ae`

### Claude

- `CLAUDE_LABELS_98.csv`: `c48535384452444fa81eee08ba593418eeef37ce16cab7811d668008d0d7a1b7`
- `CLAUDE_CODING_RECEIPT.md`: `605eb62ecd3bd279fb08a928c7d7db19c3aa09ae8c654bbf94c43a80c603f004`

## Embargo de concordancia

La concordancia Claude–Codex ya fue calculada usando solamente CaseID y etiquetas ciegas. El resultado está en:

`human_blind_v1/admin_sealed/PRELIM_CLAUDE_CODEX_AGREEMENT.json`

Sus cifras no se publican ni se envían a Telegram mientras la R1 humana siga marcada `IN_PROGRESS`, porque informar resultados externos al anotador durante su sesión violaría el cegamiento.

## Próximo paso

1. Eduardo termina R1 y exporta `HUMAN_BLIND_V1_ROUND1_LABELS.csv`.
2. Se verifica integridad y se sella su SHA-256.
3. Se calcula Krippendorff alpha nominal entre Eduardo, Claude y Codex.
4. La puerta operacional pasa con alpha >= 0.60.
5. Sólo después se libera el informe de concordancia. Esta puerta mide reproducibilidad de la rúbrica, no capacidad predictiva.
6. Si pasa, se ejecuta una sola prueba contra outcome en discovery 2022–2023; 2024 permanece cerrado para validar el futuro predictor.
