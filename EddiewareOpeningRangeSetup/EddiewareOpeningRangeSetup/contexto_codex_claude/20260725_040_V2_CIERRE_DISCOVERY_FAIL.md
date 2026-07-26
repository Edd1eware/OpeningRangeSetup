# V2 — Cierre: endpoint discovery FAIL. Score estable, sin poder predictivo.

Fecha: 2026-07-25
Fase: V2-5 ejecutada (disparo único). Ejecutor: Claude Fable.
Estado información: `V2_DISCOVERY_OPENED_ONCE_FAIL`

## 1. Veredicto

**EL SCORE MECÁNICO CONTINUO NO PREDICE EL DESPLAZAMIENTO FUTURO. LÍNEA V2
CERRADA COMO NO VALIDADA.**

```text
rho_Spearman(S, Y_60) = -0.16299
IC95 bootstrap        = [-0.39881, +0.09407]
umbral congelado      = rho >= 0.25 AND IC95_low > 0
resultado             = FAIL (falla ambas condiciones)
n pares               = 69 / 69  (mínimo exigido 56)
seed                  = 0x22f9cadf098b1625      bootstrap = 10,000 por sesión
```

El signo salió **negativo**, contrario a la hipótesis (más aceptación mecánica →
más desplazamiento). Pero el IC95 incluye el cero, así que tampoco hay evidencia
de un edge invertido explotable. La lectura correcta es: **sin señal**.

## 2. Cobertura: perfecta, el fallo no es de datos

| Componente | Resultado |
|---|---|
| `mH` (MBP-1 nueva, +65 s) | 98/98 OK |
| `m1` (MBO sellado, +5 s) | 98/98 OK |
| `OR_ticks` (snapshot sellado, 09:30) | 98/98 OK, regresión sellada PASS |
| Pares discovery válidos | 69/69 (mínimo 56) |

Cero exclusiones, cero razones de faltante. El FAIL es sustantivo, no un
artefacto de cobertura, de datos corruptos ni de muestra chica por descarte.

## 3. Qué SÍ se demostró (no es cero)

1. **El score es estable.** JOINT_STABILITY PASS: 5 perturbaciones deterministas
   con Spearman ≥0.998, cero flips fuertes, retención 100%, espejo BUY/SELL
   exacto a 1e-12. La medición es reproducible.
2. **El gate sintético ordena correctamente.** breakout > ruido > absorción en
   10/10 tripletes. La fórmula mide lo que dice medir.
3. **La distribución es sana.** S ∈ [−0.556, +0.567], mediana −0.047, simétrica
   por lado (BUY −0.049 / SELL −0.053), 20/69 en banda neutra.

Es decir: construimos un instrumento que mide de forma estable y sin sesgo la
defensa/aceptación mecánica del libro en los 5 s posteriores al burst — y ese
instrumento **no anticipa** hacia dónde se mueve el precio 60 s después.

## 4. Qué queda prohibido por el preregistro firmado

1. No hay segundo intento ni endpoint alternativo.
2. No se prueban otros horizontes (30 s, 120 s, MFE, colas).
3. No se re-ponderan componentes ni se re-normaliza contra este resultado.
4. **2024 permanece CERRADO.** La validación confirmatoria solo se autorizaba si
   discovery pasaba exacto. No pasó.
5. 2025–2026 permanece cerrado.
6. No se descarga más MBO/MBP-1 para rescatar esta línea.

Cualquier análisis adicional sobre estos 69 casos sería forking path. Se detiene
aquí por diseño, no por falta de ideas.

## 5. Integridad del experimento

- Propuestas selladas por hash antes de cruzarse (Claude `67a6d306…` / Codex
  `9131b8ad…`), preregistro convergente `22f9cadf…`, addendum `mH` `f4c5637e…`,
  contrafirma OR `319ed382…`.
- Código del extractor hasheado ANTES de tocar los 98 casos (`d9087438…`).
- Escalas calculadas solo con inputs discovery 2022–23, congeladas y reutilizadas.
- Ningún componente, peso, umbral ni horizonte se eligió mirando outcomes.
- El outcome se abrió UNA vez, después de que todo lo anterior estuviera sellado.

Este es el resultado limpio de un experimento bien hecho. El FAIL es informativo
precisamente porque no hubo grados de libertad.

## 6. Lo que este resultado descarta

La hipótesis operativa era: tras un Liquidity Burst, la mecánica del libro en los
primeros 5 s (absorción vs breakout) anticipa la dirección del movimiento
posterior. **Queda descartada para NQ con esta representación y este horizonte.**

Sumado al historial: la representación agregada MBO falló (AUC ≤0.597), la
taxonomía de precio falló (prevalencia y Jaccard), la perceptual falló
(estabilidad de la frontera C), y ahora la mecánica continua falla contra el
futuro. Cuatro representaciones distintas del mismo fenómeno, ninguna predictiva.

**La conclusión honesta es que el Liquidity Burst a 5 s no contiene información
direccional explotable en NQ.** No que "aún no encontramos la representación
correcta".

## 7. Artefactos

| Archivo | SHA-256 |
|---|---|
| V2_DISCOVERY_ENDPOINT_RESULT.json | (ver `FINAL_HASHES.sha256`) |
| V2_Y60_98.csv | idem |
| V2_OR_TICKS_98.csv | `d96cc0d6174eb1d05fec646dd10a5fef52bfe5d9f5b6bf46d0f6f40ccd61635e` |
| V2_SCORES_P0_98.csv | `da88216b95a1dd1feed2ea82eb6beb98a35b3c3817413d6d88f3d55bff1f4bdb` |
| V2_STABILITY_RESULT.json | `c969b6d79dffe4482c77b352e6691e94251d94814e91ea3cf63c6f930cd1b6a4` |

Costo total de la línea V2: USD 4.17 (descarga acotada MBP-1).

`INFORMATION_STATUS=V2_CLOSED_NOT_VALIDATED`
