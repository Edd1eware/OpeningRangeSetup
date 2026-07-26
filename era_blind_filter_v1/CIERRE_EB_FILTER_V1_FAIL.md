# EB-V1 — Cierre: filtro de 3 condiciones REPRUEBA. Y un hallazgo mayor.

Fecha: 2026-07-25
Preregistro: `45bc268309c7dba408624709e018271ab0bae8018c4ba2bd46900e47a4a77a43`
Código sellado: `51adb57b46c508b8e797f78eb64744609fa7899d4e5828baecfa06bd9c23305a`
Estado: `EB_FILTER_OPENED_ONCE_FAIL`

## 1. Veredicto: FAIL en los 5 gates

| Gate | Umbral | Obtenido | Resultado |
|---|---|---|---|
| G1 EV neto > 0 | > 0 | **−1.31 ticks** | FAIL |
| G2 PF > 1.15 | > 1.15 | **0.937** | FAIL |
| G3 Retención ≥ 40% | ≥ 40% | **25.6%** | FAIL |
| G4 Años fresh EV>0 ≥ 2 | ≥ 2 de 3 | **1 de 3** | FAIL |
| G5 Supera baseline | > −0.577 | **−1.31** | FAIL |

El filtro no solo no ayuda: **empeora** el resultado (−1.31 vs −0.577 del
baseline) y tira la frecuencia a 5.15 trades/mes.

## 2. Tabla año × métrica (comisión 2.0 ticks ya descontada)

| Bloque | Year | Trades | Trades/mes | WR % | PF | EV bruto | EV neto |
|---|---|---:|---:|---:|---:|---:|---:|
| DEV baseline | 2022 | 134 | 16.75 | 42.54 | 0.914 | +0.57 | −1.43 |
| DEV baseline | 2023 | 162 | 18.00 | 44.44 | 0.964 | +1.31 | −0.69 |
| DEV baseline | TOTAL | 296 | 17.41 | 43.58 | 0.943 | +0.97 | −1.03 |
| DEV filtrado | 2022 | 57 | 7.12 | 43.86 | 1.167 | +4.67 | **+2.67** |
| DEV filtrado | 2023 | 56 | 7.00 | 42.86 | 0.857 | −1.29 | **−3.29** |
| DEV filtrado | TOTAL | 113 | 7.06 | 43.36 | 0.985 | +1.72 | −0.28 |
| FRESH baseline | 2024 | 162 | 18.00 | 32.72 | 0.699 | −4.41 | −6.41 |
| FRESH baseline | 2025 | 162 | 20.25 | 43.83 | 1.179 | +5.30 | +3.30 |
| FRESH baseline | 2026 | 78 | 15.60 | 43.59 | 1.212 | +5.49 | +3.49 |
| FRESH baseline | TOTAL | 402 | 18.27 | 39.30 | 0.970 | +1.42 | −0.58 |
| FRESH filtrado | 2024 | 37 | 4.62 | 35.14 | 0.768 | −3.32 | −5.32 |
| FRESH filtrado | 2025 | 47 | 5.88 | 40.43 | 1.154 | +5.02 | +3.02 |
| FRESH filtrado | 2026 | 19 | 4.75 | 47.37 | 0.774 | −2.21 | −4.21 |
| FRESH filtrado | TOTAL | 103 | 5.15 | 39.81 | 0.937 | +0.69 | −1.31 |

Umbrales derivados solo de DEV: `dist_pdl p25 = ` (ver `EB_RESULT.json`),
`vol_5/vol_120 mediana DEV`. Nunca se miró FRESH antes de fijarlos.

## 3. El filtro ya era inestable en DEV (señal que no había que ignorar)

`DEV filtrado` da **+2.67 en 2022 y −3.29 en 2023**. Es decir: el filtro nunca
funcionó de forma consistente ni siquiera en el bloque de diseño. No es un caso
de "funcionó en dev y murió en fresh" — nunca funcionó. En 2026 vuelve a
invertirse (+3.02 en 2025, −4.21 en 2026).

## 4. HALLAZGO MAYOR (más importante que el FAIL)

La tabla revela algo que no era el objeto del test pero cambia las prioridades:

**La regla base — OR breakout en ambas direcciones con trailing 50/20/40 — NO es
rentable neta de comisión.**

```text
EV bruto TOTAL (698 sesiones) = +1.23 ticks
comisión                       = −2.00 ticks
EV neto                        = −0.77 ticks
```

- DEV (2022-23): EV neto −1.03, PF 0.943
- FRESH (2024-26): EV neto −0.58, PF 0.970
- Solo 2025 y 2026 son positivos; 2024 pierde −6.41 neto por trade.

Los 2 ticks de comisión se comen el edge bruto completo. Con WR ~43% y PF ~0.95,
esto es un sistema perdedor sostenido por dos años buenos.

**Implicación:** filtrar *este* baseline es optimizar sobre una base negativa.
Ningún filtro de participación lo va a salvar salvo que descarte casi todo — y
entonces muere la frecuencia, que es tu criterio prioritario.

## 5. Qué queda prohibido (preregistro)

No se prueban variantes `>=1` ni `>=3` condiciones, ni otras columnas de PnL, ni
otro split, ni excluir 2024. FAIL es FAIL. La línea del filtro de 3 condiciones
sobre este baseline se cierra aquí.

## 6. Nota de honestidad

Los artefactos del test era-blind original del 02-jul (carpeta `Codex_cotexto`)
no existen. Estas tres condiciones son **reconstrucciones** de aquellas familias,
no las definiciones exactas que pasaron. Es posible que las originales fueran
distintas y mejores. Lo que este test sí establece con solidez es el punto 4: el
baseline no aguanta comisión.

`INFORMATION_STATUS=EB_FILTER_CLOSED_FAIL`
