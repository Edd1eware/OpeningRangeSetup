# 050 — V4 breadth 2/3 falla en DEV

Fecha: 2026-07-26  
Veredicto: **FAIL_DEV**

Regla sellada: primer breakout NQ solo si al menos 2 de ES/YM/RTY ya aceptan
fuera de su OR en el mismo sentido. Prerregistro:
`4674221355ddcebe513f2ef5c03b3256db2a4e4c0b5d32ab1c502a2a07d5a5e1`.

## DEV 2022-04-25..2023-12-31

| n | EV trailing | PF | Años + | Semestres + |
|---:|---:|---:|---:|---:|
| 64 | -0.02381R | 0.9546 | 1/2 | 50% |

Fixed 1R dio EV `-0.05295R`, de modo que el trailing mejora `+0.02914R` pero
no crea edge.

La adquisición YM+RTY fue limitada a 09:25–10:05 NY. Tras el fallo DEV se
detuvo: 518 archivos completos, 25.33 MB, cero parciales. No se evaluó
PSEUDO_VAL ni se abrió HOLDOUT.

Conclusión: la confirmación amplia no rescata el ORB NQ. La siguiente prueba
habilitada es V5, que espera cinco barras posteriores al primer Liquidity Burst
publicado y separa aceptación de reclaim sin usar 2024.

Artefactos:

- resultado SHA-256
  `575D1BE0051FCC78ECEDFD6D68932B643883F9D55CC2CF085E8ECF7C7E8F3782`;
- trades SHA-256
  `9DDC99500AA578E5D0DCD7CD72378F0220291B78BFF05F475EAA394AD44FD093`.

`INFORMATION_STATUS=LUCID150K_SNIPER_V4_DEV_FAIL_DOWNLOAD_STOPPED`
