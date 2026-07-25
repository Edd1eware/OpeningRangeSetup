# Contrafirma Codex — V2-1

Fecha: 2026-07-25  
Documento contrafirmado: `V2_PREREGISTRO_CONVERGENTE.md`  
SHA-256 del preregistro contrafirmado: `22f9cadf098b1625a89046ed5bfbe8f27cace3f29f05f8b78105a841b4094f9a`

## Veredicto

**FIRMADO**

Codex acepta como especificación normativa la propuesta
`codex_sealed/CODEX_V2_PROPOSAL.md` íntegra, complementada por las enmiendas
A1, A2 y A3 de `V2_PREREGISTRO_CONVERGENTE.md`.

## Verificaciones realizadas

1. **Integridad de la propuesta Codex.** Calculé SHA-256 sobre los bytes del
   archivo sellado. Resultado:
   `9131b8ad7e586c0dcf991a7d75050624c038903acf55360c8eee52b4cd19e8ea`.
   Coincide exactamente con el hash citado en el preregistro.
2. **Integridad cruzada de la propuesta Claude.** El SHA-256 calculado fue
   `67a6d306389c8332128f6f089303ad9204882ba5ec1c38d0ea6a39f7a5e395cc`,
   también coincidente con el preregistro.
3. **Base normativa.** Verifiqué que la sección 2 incorpora íntegramente, sin
   sustituciones normativas, las secciones 0–10 de la propuesta Codex: 13
   componentes y tres pilares; orientación por `sigma`; regla atómica `F_LAST`;
   normalización sin centrado `tanh(r/s_j)` y floors; score y cobertura por
   bloques; banda `±0.15`; `P1:P5+MIRROR`; gates; endpoint único `Y_60`; criterio
   de éxito; y condiciones auditables para abrir 2024.
4. **Enmienda A1.** Es fiel al gate sintético propuesto por Claude y compatible
   con la propuesta Codex. Complementa, sin reemplazar, `MIRROR`; ocurre antes de
   los casos reales, no usa outcomes y un FAIL solo permite corregir un bug de
   implementación.
5. **Enmienda A2.** Es compatible con ambas propuestas como análisis secundario
   obligatorio de 2024. No altera el endpoint ni el veredicto primario y no
   habilita selección por lado, ocultamiento ni una segunda apertura.
6. **Enmienda A3.** Es fiel a la regla Codex de derivar el seed de los primeros
   64 bits del SHA-256 del preregistro y la extiende de forma determinista al
   bootstrap de 2024, sin grado de libertad post hoc.
7. **Divergencias.** Verifiqué que las resoluciones adoptan de forma coherente la
   propuesta Codex como base y añaden únicamente A1/A2/A3. Las concesiones de la
   propuesta Claude quedan identificables y no cambian de forma silenciosa los
   signos, pesos, escalas, cobertura, horizonte o umbrales.
8. **Outcome-blindness y handoff.** La convergencia no usa outcomes, mapping,
   etiquetas AMD, MFE/MAE/TP/SL/PnL ni fuentes nuevas. El orden congelado impide
   abrir outcomes antes de integridad, calibración sintética y estabilidad, y
   prohíbe endpoint alternativo, segunda apertura y cambios post-firma.
9. **Alcance de esta revisión.** Solo abrí el preregistro y las dos propuestas
   selladas autorizadas. No abrí mapping, outcomes ni `admin_sealed`, y no
   modifiqué ningún archivo sellado.

## Observaciones menores no bloqueantes

- En la fila **Componentes**, el paréntesis enumera K4, K6, B4 y B5, pero omite
  `F2` (`F_area_flujo`) entre las diferencias respecto de los ocho componentes
  Claude. No crea ambigüedad normativa porque la sección 2 adopta expresamente
  los 13 componentes y la propuesta Codex íntegra.
- La resolución de la fila **2024 por lado** llama a A2 “gate secundario”. Se
  entiende conforme al texto normativo de A2: es una obligación de cálculo y
  publicación, no un criterio de PASS/FAIL ni de VALIDADO/NO VALIDADO.
- La tabla no detalla que las familias de perturbaciones de ambas propuestas
  también diferían. La resolución queda, no obstante, cerrada por la adopción
  explícita de `P1:P5+MIRROR` de Codex en las secciones 2, 3 y 5.

Estas observaciones son editoriales y no condicionan la firma ni autorizan
modificar el preregistro después de esta contrafirma.

`INFORMATION_STATUS=CODEX_COUNTERSIGNED_V2_PREREG_NO_OUTCOME`
