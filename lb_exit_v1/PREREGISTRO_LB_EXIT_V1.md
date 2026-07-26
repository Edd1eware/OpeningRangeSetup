# Preregistro LB-EXIT-V1 — Liquidity Burst como señal de SALIDA

Fecha: 2026-07-25
Autor: Claude Fable
Estado: **CONGELADO ANTES DE EJECUTAR**

## 0. Origen y contaminación (declarado)

La idea nace de `H3_INFORME_FINAL.md`: en 2025-2026, los días con LB tienen
EV neto −4.48 y los días sin LB +10.10. Pero **el 82% de los LB ocurre DESPUÉS de
la entrada** (mediana +59 s), así que como filtro de entrada es lookahead.

El reencuadre causal es: *el LB no dice si entrar, dice si salir*. Esa pregunta
—**dado que el LB dispara con la posición abierta, ¿salir ahí bate a mantener?**—
**nunca se ha examinado en ningún dato.**

Mitigación de contaminación:

| Conjunto | Rol | Motivo |
|---|---|---|
| **2022-2024** | **PRIMARIO** (disparo único, con gate) | Nunca examinado para nada de timing de salida. El sesgo de selección de días (86-94% con LB) NO afecta una comparación *dentro* del trade condicionada a que el LB ocurra |
| 2025-2026 | Confirmación descriptiva | La motivación salió de aquí; no otorga veredicto |

## 1. Reconstrucción exacta del trade (sin lookahead)

Se reutiliza literalmente la lógica congelada de `orb_trailing_sim.py`:

```text
datos      = raw_dbn_2\<fecha>\ohlcv-1s-full  (barras 1s)
OR         = 13:30:00-13:31:00 UTC   (09:30-09:31 ET)
entrada    = primer cierre de barra que perfora OR high (UP) u OR low (DOWN),
             a partir de 13:31:00, al nivel del OR
gestion    = trail_50_20_40  ->  sl=50, act=20, dist=40 ticks
             regla barra a barra conservadora, sin lookahead intrabar
             fin de sesion -> salida a cierre
comision   = 2.0 ticks (identica en ambos brazos, 1 round trip)
tick       = 0.25 ; USD 5 por tick
```

## 2. La regla bajo prueba

```text
t_LB = timestamp del PRIMER Liquidity Burst del dia (burst_events.csv)

BRAZO A (mantener)  = trail_50_20_40 puro, tal cual
BRAZO B (salir en LB) = identico, pero si t_LB cae DESPUES de la entrada y
                        ANTES de que el trailing cierre la posicion,
                        se sale al CIERRE de la barra de 1s que contiene t_LB
```

**Población evaluada:** únicamente los trades donde el LB dispara con la posición
abierta (`entrada < t_LB < salida_del_trailing`). Comparar sobre otros trades
sería confundir el efecto con selección de días.

La comparación es **pareada**: mismos trades, dos gestiones. Elimina el sesgo de
selección de la muestra 2022-2024.

## 3. Gate de éxito (los cuatro, sobre 2022-2024)

| # | Criterio | Umbral |
|---|---|---|
| G1 | Mejora media de B sobre A | **≥ +2.0 ticks/trade** |
| G2 | IC95 bootstrap de la mejora excluye 0 | 10,000 réplicas, seed `0x22f9cadf098b1625` |
| G3 | Mejora > 0 en ≥ 2 de los 3 años | 2022, 2023, 2024 |
| G4 | n de trades afectados | ≥ 40 |

Se exige margen económico (≥2 ticks), no solo significancia: una mejora de 0.3
ticks sería estadística pero inútil tras costes de ejecución.

PASS en los cuatro = **candidata**, y solo entonces se reporta 2025-2026 como
confirmación descriptiva. Un fallo = rechazada, sin reintentos.

## 4. Prohibiciones

No se prueban otras definiciones de `t_LB` (siempre el primero del día). No se
prueban otras gestiones base (siempre `trail_50_20_40`). No se prueba salida
parcial, ni reversa, ni retardo tras el LB. No se excluye ningún año. No se
cambia el umbral tras ver el resultado. Si falla, se documenta y se cierra.

`INFORMATION_STATUS=LB_EXIT_V1_PREREGISTERED_NO_RESULT`
