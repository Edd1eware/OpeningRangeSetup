# Resultado DEV — LUCID150K-SNIPER-V4-BREADTH

Fecha: 2026-07-26  
Prerregistro:
`4674221355ddcebe513f2ef5c03b3256db2a4e4c0b5d32ab1c502a2a07d5a5e1`  
Veredicto: **FAIL_DEV / NO PSEUDO / NO HOLDOUT**

## Integridad

- DEV completo: 414 sesiones NQ/ES/YM/RTY, DST-aware.
- 0 errores.
- 64 trades.
- YM+RTY se adquirieron outcome-blind en 09:25–10:05 NY.
- Al fallar DEV, la descarga posterior se detuvo.
- Quedaron 518 archivos válidos, 25.33 MB y 0 parciales.
- PSEUDO no fue evaluado y HOLDOUT permanece intacto.

## Resultado

| Métrica | Trailing | Fixed 1R diagnóstico |
|---|---:|---:|
| n | 64 | 64 |
| EV | -0.02381R | -0.05295R |
| PF | 0.9546 | 0.8990 |
| Años positivos | 1/2 | 0/2 |
| Semestres positivos | 50% | 50% |

El trailing aporta `+0.02914R/trade` frente a fixed, pero el setup sigue sin
edge. Disposición de 414 sesiones:

```text
breadth <2: 341
riesgo fuera de 20..80: 9
trades: 64
```

EV anual trailing:

```text
2022 +0.00776R
2023 -0.05347R
```

## Conclusión

Exigir que al menos dos de ES/YM/RTY estén fuera de su OR en el mismo sentido
no mejora el primer breakout NQ. El efecto ES-confirm prometedor anterior era
infra-potenciado y no se fortalece al añadir breadth amplio.

SHA-256:

- resultado DEV:
  `575D1BE0051FCC78ECEDFD6D68932B643883F9D55CC2CF085E8ECF7C7E8F3782`;
- trades DEV:
  `9DDC99500AA578E5D0DCD7CD72378F0220291B78BFF05F475EAA394AD44FD093`.

`INFORMATION_STATUS=LUCID150K_SNIPER_V4_DEV_FAIL_DOWNLOAD_STOPPED`
