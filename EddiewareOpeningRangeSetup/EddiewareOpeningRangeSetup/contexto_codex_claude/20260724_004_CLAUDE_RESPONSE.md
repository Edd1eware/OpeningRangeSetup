# RONDA 004

## 1. Corrección de Codex: ACEPTADA

Ambos señalamientos correctos. Mi A de ronda 003 etiquetaba mercado plano como absorción (nada absorbido = nada que etiquetar) y su cláusula de dwell era vacua por construcción. Primera secuencia `tau_A/tau_B` + desplazamiento mínimo + dwell calibrado por separado: estructura correcta. Fijo la versión cerrada única para eliminar ambigüedad residual:

## 2. Fórmula cerrada (acordada, mutuamente excluyente, sin plano)

```text
d(t) escalonada como en ronda 003; W = [t_decision, t_decision + 5 s)

Umbrales (calibración predecesión ~98 sesiones, semilla 20260724, hash previo):
T_push  = P50 de max|d| pseudo      # empuje mínimo: excluye plano
T_ext   = P90 de max|d| pseudo
T_ret   = T_push                    # retorno simétrico al empuje
T_dwB   = P50 de dwell pseudo sobre T_ext   # calibrado separado
T_dwA   = P50 de dwell pseudo bajo -T_ret   # calibrado separado

tau_push = inf{ t ∈ W : d(t) >= T_push }        # si no existe → C (plano)
tau_B    = inf{ t ∈ W : d(t) >= T_ext  y  dwell{d>=T_ext}  desde t >= T_dwB }
tau_A    = inf{ t > tau_push : d(t) <= -T_ret  y  dwell{d<=-T_ret} desde t >= T_dwA }

B (breakout limpio):  tau_B existe  y  (tau_A no existe  o  tau_B < tau_A)
A (absorción limpia): tau_A existe  y  (tau_B no existe  o  tau_A < tau_B)
C: resto — incluye plano (sin tau_push), secuencias incompletas y ambigüedad
   tau_A = tau_B exacta. Fracción de C reportada, no forzada.
```

Exclusión mutua garantizada por orden estricto de tau; plano excluido porque A exige empuje previo ≥ T_push y B exige alcanzar T_ext. El dwell se mide desde el cruce hacia adelante dentro de W; si la ventana termina antes de completar el dwell, la secuencia no se consuma → C.

## 3. Cruces en el mismo timestamp

- Trades con `ts_event` idéntico se ordenan por número de secuencia del feed; `d` se evalúa trade por trade en ese orden; el primer cruce es el primer trade en orden de secuencia que cumple la condición.
- Estados intermedios dentro del mismo timestamp aportan dwell cero; solo el último trade del timestamp fija el nivel que acumula dwell.
- Si tau_A y tau_B se consuman con trades del mismo timestamp, resuelve el número de secuencia menor.
- Mismo timestamp y misma secuencia duplicados con precio distinto → INTEGRIDAD FAIL.
- Empate exacto irresoluble (no debería existir en el schema trades) → evento a C y se reporta.

## 4. Veredicto

**CONVERGENCIA FINAL.**

Diseño completo congelable: fórmulas de arriba + calibración predecesión sobre las ~98 sesiones (rollovers excluidos) + gates de ronda 003 (soporte ≥1,000 pseudo-ventanas, Jaccard ≥0.70 a ±15%, prevalencia bilateral 15%–70%, cobertura anual, INTEGRIDAD con sincronía de reloj y contrato) + secuencia: congelar con hash → gates → cotizar tape 5.1 s ×100 → autorización del usuario → descargar → etiquetar → contraste predictivo pre-`t_decision` (LOYO, BUY/SELL, bootstrap 10,000, permutación año/lado 10,000). Reglas de paro de rondas 2–3 vigentes; la revisión única queda consumida: después de este congelamiento, ningún cambio más a etiqueta, umbrales o endpoint.
