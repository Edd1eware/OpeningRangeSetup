# Errata inmutable — Mechanical Book Outcome V1

Fecha UTC: 2026-07-24T18:51:52Z  
Estado: **V1 CERRADO / FAIL — sin rescate**  
Tipo: corrección semántica y documental; no reejecución

## Artefactos originales preservados

| Artefacto | SHA256 |
|---|---|
| `20260724_021_PREREGISTRO_MECHANICAL_BOOK_V1.md` | `9c804cab08fc3e4c457909906254feebe8a3c1bd169aa5b503436bf03a046541` |
| `MECHANICAL_BOOK_V1_RESULT.json` | `e1307ffdd30a1147beebf84cc3d9690bffd65518ed2811252019f19b0a53d850` |
| `MECHANICAL_BOOK_V1_LABELS_98.csv` | `bfddb850bbcfce5fc7ccebd0a96a08473909c32496208d254b3fa2386c100513` |
| `MECHANICAL_F_C_AUDIT_RESULT.json` | `08d4ac4f4a3e52f194ee8b3255a30106d2c7d6148c87c47189ca9a69d15538c9` |

Ninguno de estos archivos fue sobrescrito. Las 98 etiquetas, las constantes,
el horizonte de cinco segundos y `instrument_pass=false` permanecen
exactamente como se publicaron.

## Corrección F/C

La puerta de implementación `fills_reconciled_with_C` no pertenecía a los
gates congelados y su semántica era demasiado estricta:

- `F` informa una ejecución pero no muta el libro;
- una ejecución parcial puede actualizar el tamaño visible mediante `M`;
- una ejecución total normalmente actualiza mediante `C`;
- una orden iceberg puede reponer tamaño visible, de modo que la mutación
  `M` puede mantener o aumentar la profundidad después de `F`;
- el estado sólo se inspecciona al recibirse `F_LAST`.

Evidencia sobre las 98 sesiones:

| Medida | Resultado |
|---|---:|
| Cantidad `F` en L0 contada por V1 | 1,174 |
| Llaves evento/orden/precio con `F` | 1,120 |
| Llaves con `C` de la misma identidad | 1,080 (96.43%) |
| Cantidad explicada por reducción `M` | 36 |
| Cantidad sin reducción contemporánea M/C | 18 |
| De esos 18: reposición/iceberg pasivo | 12 |
| De esos 18: `F` de la orden agresora | 6 |

Los 54 contratos que la implementación denominó "`F` sin `C`" quedan
explicados por:

```text
36  fill parcial con reducción M
12  fill pasivo con reposición/iceberg
 6  F de la propia orden agresora
--
54
```

Por lo tanto, `fills_reconciled_with_C=false` es un diagnóstico inválido como
puerta de integridad. No indica corrupción del MBO. Se conserva únicamente
como antecedente de la implementación original.

Referencias de semántica:

- [Databento: state management of resting orders](https://databento.com/docs/examples/order-book/order-tracking)
- [Databento: GLBX.MDP3 normalization](https://databento.com/docs/knowledge-base/datasets)

## Defecto menor de diseño: aggressor-F

En GLBX.MDP3 puede emitirse un `F` para la orden agresora cuando esa orden ya
existía en el libro. Se identifica porque el `order_id` de `F` coincide con el
`order_id` de `T` en el mismo Trade Summary.

V1 incluyó seis contratos de este tipo en `F_dep`, repartidos en cuatro
sesiones. Eso no representa liquidez pasiva atacada. La definición futura de
`F_dep` deberá excluirlos.

Prueba de materialidad, sin reetiquetar:

| Fecha | `F_dep` original | `F_dep` sin aggressor-F | Base / h=.425 / h=.575 |
|---|---:|---:|---|
| 2023-05-18 | 39 | 38 | C / C / C |
| 2023-08-24 | 40 | 39 | C / C / C |
| 2023-09-19 | 40 | 39 | C / C / C |
| 2024-06-05 | 15 | 12 | C / C / C |

Las etiquetas son invariantes; no se reemiten.

## Veredicto que no cambia

Mechanical Book V1 sigue cerrado porque falló gates que sí estaban
prerregistrados:

- A=2/98 y B=2/98, ambos por debajo de 15%;
- A sólo aparece en 2022;
- B sólo aparece en 2023;
- no hay cobertura A/B estable por año y lado;
- Jaccard B=.667/.500, por debajo de .70.

Quitar una puerta no prerregistrada no convierte el instrumento en PASS y no
autoriza ajustar `h`, horizonte, nivel, población ni reglas.

## Prohibiciones heredadas

- No entrenar clasificador con estas cuatro etiquetas limpias.
- No descargar más MBO para rescatar V1.
- No ejecutar ATAS.
- No usar MFE, MAE, TP, SL o PnL como predictor ni como ground truth mecánico.
- No tocar 2025–2026.

