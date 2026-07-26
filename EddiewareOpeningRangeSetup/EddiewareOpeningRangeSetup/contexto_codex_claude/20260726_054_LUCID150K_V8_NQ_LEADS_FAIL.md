# 054 — V8 NQ líder falla con muestra amplia

Fecha: 2026-07-26  
Veredicto: **FAIL_DEV**

El primer breakout NQ con al menos dos de ES/YM/RTY neutrales y cero oposición
dio n=248, EV `-0.0964R`, PF `0.8172`, 0/2 años positivos y solo 25% de
semestres positivos. La frecuencia fue 11.81/mes, por lo que no es un fallo de
potencia.

Fixed 1R también pierde `-0.0564R`; trailing empeora `-0.0400R`.

Siguiente hipótesis: no invertir la curva directamente. Exigir primero conflicto
cross-market >=2 instrumentos en el lado opuesto y luego reclaim NQ dentro de
15 segundos antes del fade.

SHA-256 resultado
`4E0E78F3DAC80B6ADF608D3CCF239759BBE65151EF952DE71B149A9F9AD5172D`.

`INFORMATION_STATUS=LUCID150K_SNIPER_V8_NQ_LEADS_FAIL`
