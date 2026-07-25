# Claude–Codex convergence request after AMD-2 stability result

No mapping or outcome has been opened.

## Frozen AMD-2 result

- Original consensus: A=27, B=35, C=36.
- Primary denominator: 62 original A/B.
- Frozen rule counted A/B->C or A<->B as flip.
- Frozen PASS: flip rate <=10%.
- Observed: 9/62 = 14.516%; FAIL.
- Exact consensus original vs perturbed over all 98: 82/98 = 83.67%.
- New consensus: A=27, B=33, C=38.

Transitions:

- A->A: 20
- A->C: 7
- B->B: 33
- B->C: 2
- C->A: 7
- C->C: 29
- A<->B directional flips: 0
- Original A/B retained with same direction: 53/53

The instability is entirely the C/abstention boundary. Direction A vs B never reversed.

## User directive

The user explicitly ordered using Claude–Codex, ignoring the human coder and proceeding. They also require Claude and Codex to converge before major direction changes.

## Questions

1. Must the AMD-2 FAIL remain final for this representation, despite zero directional flips?
2. Is it legitimate, before any outcome, to define an AMD-3 stable-core classifier:
   - A only if original consensus A AND perturbed consensus A;
   - B only if original consensus B AND perturbed consensus B;
   - all else C;
   yielding A=20, B=33, C=45?
3. Could AMD-3 run the already frozen discovery outcome endpoint once without lookahead, while clearly labeled as a new post-stability amendment rather than an AMD-2 success?
4. Or must we instead create genuinely new stimuli/data before any outcome test?
5. Give exact next steps that best honor both statistical integrity and the user's directive to proceed.

Do not read labels case by case, mappings, dates, outcomes, MFE, MAE, TP, SL or PnL. Read only the frozen protocol files and this prompt if needed. Respond by stdout; do not modify files.
