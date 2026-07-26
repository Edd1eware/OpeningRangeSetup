# Addendum convergente V2-5 — fuente de `mH` (firmado Claude + Codex)

Fecha: 2026-07-25
Alcance: preregistra ÚNICAMENTE la fuente de `mH`. El endpoint `Y_60`, el score,
las escalas, los gates, el bootstrap y el umbral de éxito NO cambian.

## 1. Protocolo de independencia cumplido

| Propuesta | SHA-256 | Sellada antes de ver la otra |
|---|---|---|
| Claude `CLAUDE_MH_SOURCE_PROPOSAL.md` | `39d4775294db50162f35d89d016430bfe4c43670c77026770e2a2f2f2696f3b9` | Sí (hash publicado antes de lanzar Codex) |
| Codex `codex_sealed/CODEX_MH_SOURCE_PROPOSAL.md` | `e0139d2b9b88baf53399c4ef2c6b61b483861d103ef3f6fbdadbb8b0688df277` | Sí (verificado: no leyó la de Claude) |

Ambos hashes verificados post-entrega: intactos.

## 2. Convergencia

Coincidencia independiente en TODO lo sustantivo: dataset `GLBX.MDP3`, schema
`mbp-1`, `stype_in=raw_symbol` con el `resolved_raw_symbol` congelado, ventana
`[cutoff+64.000 s, cutoff+65.050 s)`, `m1` desde el MBO sellado (no se
redescarga), antigüedad máxima 1.000 s, cobertura mínima 56, horizonte +60 s
inalterado. Cero divergencias sustantivas.

**Base normativa: la propuesta Codex íntegra**, por ser un superconjunto más
preciso. Aporta sobre la de Claude: exclusión explícita de registros con
`ts_recv > tH` del cálculo (los 50 ms son solo margen de adquisición, se
conservan para auditoría); definición de BBO completo (`bid_px_00` y `ask_px_00`
válidos y `ask >= bid`); desempate por secuencia del feed y luego orden físico;
aritmética en representación entera/fixed-price de Databento antes de convertir
unidades para evitar error binario; admisión de midpoints de medio tick;
`ts_recv` como reloj normativo; y códigos de razón mecánica por exclusión.

## 3. Especificación congelada

```text
dataset  = "GLBX.MDP3"
schema   = "mbp-1"
symbols  = [resolved_raw_symbol del evento]      stype_in = "raw_symbol"
ventana  = [cutoff + 64.000 s, cutoff + 65.050 s)     (end exclusivo, ts_recv)

tH = cutoff + 65.000 s = t1 + 60.000 s
mH = (bid_px_00 + ask_px_00)/2 del ÚLTIMO BBO completo con ts_recv <= tH,
     válido solo si 0 <= tH - ts_BBO <= 1.000 s
m1 = midpoint del último BBO completo anterior a t1, desde el MBO YA SELLADO
Y_60 = sigma * [(mH - m1)/delta_p] / max(OR_ticks, 1)
endpoint = rho_Spearman(S, Y_60)
éxito = rho_hat >= 0.25 AND IC95_low > 0   (bootstrap 10,000 por sesión,
        seed 0x22f9cadf098b1625)
```

Faltante de `mH` (sin BBO completo válido, contrato no resuelto, respuesta vacía
o corrupta): el caso se excluye con razón mecánica registrada, sin mirar signo ni
magnitud de `Y_60`. Cobertura mínima 56 pares válidos; por debajo, discovery es
`FAIL_COVERAGE` y NO se extiende ventana, ni se cambia schema, ni horizonte, ni
endpoint.

## 4. Costo autorizado

Cotización `metadata.get_cost` (gratuita, ya ejecutada): **USD 4.173532** total,
máximo USD 0.075756 por evento, 98 peticiones. Autorizado por el usuario
(opción 1). Tope duro: USD 5.00. Si el costo real excediera el tope, se aborta.

## 5. Prohibiciones vigentes

No descargar nada para `m1`, features, Opening Range, otros contratos, fechas,
schemas, proveedores ni endpoints. No ampliar la ventana para rescatar faltantes.
No probar otros horizontes. No optimizar contra outcome. Sellar los DBN, el
manifiesto y sus hashes antes de cualquier apertura de outcomes.

Firmas: Claude Fable + Codex (convergencia por propuestas selladas independientes).

`INFORMATION_STATUS=MH_SOURCE_PREREGISTERED_NO_OUTCOME`
