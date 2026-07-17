# Reanudación segura de Historia X10 — 17/07/2026

## Punto de reanudación

- Próxima sesión: `2025-08-07`.
- Última sesión terminal preservada: `2025-08-06` (`TP`).
- ATAS permanece abierto; no se reinició la aplicación.
- Balance, CSV, timelines y estado de Telegram no se reiniciaron.
- Velocidad confirmada visualmente por UI Automation: `10x`.

## Hallazgo operativo

El movimiento errático del puntero no provenía de la estrategia ni del
supervisor. La ruta concreta era `paste_text()` del runner común, que ejecutaba
`DateEdit.click_input()` antes de reemplazar el valor. Cuando ATAS rechazaba un
rango, el bucle reintentaba tres veces y luego continuaba con la siguiente fecha;
por eso el puntero seguía moviéndose después del primer hueco.

## Contención aplicada

La reanudación usa `resume_replay_x10_uia_failfast.py`, un adaptador de transporte
que no modifica la DLL, Liquidity Burst, entradas, salidas, TP/SL, CVD ni la lógica
de sincronización del Replay:

1. Los campos FROM/TO se escriben con UIA `ValuePattern.SetValue`.
2. Los botones Stop se ejecutan con UIA `InvokePattern`.
3. El Start queda a cargo del supervisor existente, también mediante
   `InvokePattern`.
4. Cualquier intento inesperado de clic físico se bloquea.
5. El primer fallo de fecha detiene toda la corrida y conserva esa fecha como
   próximo punto de reanudación.
6. El historial de Telegram y el balance se preservan.
7. El análisis global de familias queda diferido hasta completar los huecos
   históricos; no se publicarán conclusiones parciales.

## Invariantes

- Modo: Historia X10 únicamente.
- Replay X1: deshabilitado.
- Sin `--reset-state`.
- Sin `--force`.
- Sin recompilar ni copiar DLL.
- Sin cambios en lógica de trading o Replay.
