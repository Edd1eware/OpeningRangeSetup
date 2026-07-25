# RUNBOOK — Separación A/B en ORB NQ

Ejecutable en terminal, fase por fase. **Cada fase termina en una GATE que debe imprimir `PASS` antes de continuar.**

Regla dura: no se avanza de fase con una GATE en `FAIL`. No se edita el umbral para que pase.

```
FASE 0  Test Cero            gratis, sin MBO, puede cerrar el programa
FASE 1  Trabajo sobre las 6  gratis, ya tienes los datos
FASE 2  Congelar preregistro hash + tag
FASE 3  Censo                solo si 0 y 1 pasan
```

---

## Setup

```bash
cd ~/OpeningRangeSetup
mkdir -p research/ab_separation/{src/common,data/{raw,interim,events},out/{f0,f1a,f1b,f1c,f1d}}
cd research/ab_separation

python -m venv .venv && source .venv/bin/activate
pip install numpy pandas scipy duckdb pyarrow databento matplotlib

cat > .gitignore << 'EOF'
data/raw/
.venv/
__pycache__/
EOF
```

Config única. **Los tres números de §7 del preregistro van aquí y no se tocan después de congelar.**

```bash
cat > src/common/config.py << 'PYEOF'
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT  = ROOT / "out"
DATA = ROOT / "data"

# ---- Umbrales de la regla (congelados, §5.2) ----
RATIO_IMBALANCE = 3.0
VOL_MIN_CELDA   = 70
NIVELES_APILADOS = 3
DIST_BORDE_TICKS = 20

# ---- Decisión (§7). RELLENAR ANTES DE CONGELAR ----
MDE_PREREG   = None    # efecto mínimo de interés, en unidades de MFE/ORTicks
UMBRAL_EXITO = None    # IC95% inferior debe superarlo
ALPHA        = 0.05
POWER_TARGET = 0.80

N_BOOT = 10_000
SEED   = 42

# ---- Sesión ----
TZ = "America/Chicago"
RTH_OPEN  = "08:30:00"
OR_END    = "08:31:00"   # ver nota de scorer vs execution manager
PYEOF
```

---

# FASE 0 — Test Cero

**Pregunta:** ¿A y B difieren en distribución de resultado?
**Costo:** cero. No requiere MBO ni Databento. Solo tu histórico etiquetado en ATAS.
**Si no difieren, el programa termina aquí** y te ahorra todo lo demás.

## 0.1 Input

Exporta tu histórico completo 2022–2024 a `data/events/ab_labeled.parquet` con este esquema:

| columna | tipo | nota |
|---|---|---|
| `date` | date | clave de bloque para el bootstrap |
| `contract` | str | NQM2, NQU2, … |
| `side` | str | BUY / SELL |
| `pattern` | str | A / B |
| `or_ticks` | float | denominador de normalización |
| `mfe_ticks` | float | |
| `mae_ticks` | float | |
| `t_decision` | timestamp | |

> `pattern` sale de tus reglas de footprint. `mfe/mae` de tu backtest. **Nada de MBO aquí.**

## 0.2 Bootstrap por bloques

```bash
cat > src/common/bootstrap.py << 'PYEOF'
import numpy as np
from scipy.stats import norm


def day_blocks(df, value_col, group_col, ga, gb, day_col="date"):
    """Una sesión = un bloque. Preserva la dependencia intradía."""
    blocks = []
    for _, g in df.groupby(day_col, sort=True):
        a = g.loc[g[group_col] == ga, value_col].to_numpy(dtype=float)
        b = g.loc[g[group_col] == gb, value_col].to_numpy(dtype=float)
        blocks.append((a, b))
    return blocks


def bootstrap_diff(blocks, n_boot=10_000, seed=42):
    rng = np.random.default_rng(seed)
    n = len(blocks)
    out = np.empty(n_boot)
    out[:] = np.nan
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        a = np.concatenate([blocks[j][0] for j in idx])
        b = np.concatenate([blocks[j][1] for j in idx])
        if a.size and b.size:
            out[i] = a.mean() - b.mean()
    return out[~np.isnan(out)]


def observed_diff(blocks):
    a = np.concatenate([b[0] for b in blocks])
    b_ = np.concatenate([b[1] for b in blocks])
    return a.mean() - b_.mean(), a.size, b_.size


def power_normal(delta, se, alpha=0.05):
    """Potencia usando el SE del block bootstrap (respeta la dependencia)."""
    z = norm.ppf(1 - alpha / 2)
    return 1 - norm.cdf(z - delta / se) + norm.cdf(-z - delta / se)


def mde(se, alpha=0.05, power=0.80):
    return se * (norm.ppf(1 - alpha / 2) + norm.ppf(power))
PYEOF
```

## 0.3 Runner

```bash
cat > src/f0_test_cero.py << 'PYEOF'
import sys, json
import numpy as np, pandas as pd
from common.config import *
from common.bootstrap import *

df = pd.read_parquet(DATA / "events" / "ab_labeled.parquet")

# --- Guardas de integridad ---
assert df["pattern"].isin(["A", "B"]).all(), "pattern fuera de {A,B}"
assert (df["or_ticks"] > 0).all(), "or_ticks no positivo"
assert df[["mfe_ticks", "mae_ticks"]].notna().all().all(), "outcome con NaN"

df["mfe_norm"] = df["mfe_ticks"] / df["or_ticks"]
df["mae_norm"] = df["mae_ticks"] / df["or_ticks"]
df["date"] = pd.to_datetime(df["date"]).dt.date

print(f"n = {len(df)}  |  A = {(df.pattern=='A').sum()}  B = {(df.pattern=='B').sum()}  |  sesiones = {df.date.nunique()}")

results = {}
for metric in ["mfe_norm", "mae_norm"]:
    blocks = day_blocks(df, metric, "group_col" if False else "pattern", "A", "B")
    blocks = [b for b in blocks if b[0].size and b[1].size]
    if len(blocks) < 30:
        print(f"AVISO: solo {len(blocks)} sesiones con ambas clases. IC poco fiable.")
    d_obs, nA, nB = observed_diff(blocks)
    boot = bootstrap_diff(blocks, N_BOOT, SEED)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    se = boot.std(ddof=1)
    results[metric] = dict(diff=float(d_obs), lo=float(lo), hi=float(hi), se=float(se),
                           nA=int(nA), nB=int(nB), n_blocks=len(blocks),
                           mde_80=float(mde(se, ALPHA, POWER_TARGET)))
    print(f"\n[{metric}]  A-B = {d_obs:+.4f}   IC95% [{lo:+.4f}, {hi:+.4f}]   SE = {se:.4f}")
    print(f"           MDE al 80% de potencia = {results[metric]['mde_80']:.4f}")

# --- GATE §7 ---
print("\n" + "=" * 60)
if MDE_PREREG is None or UMBRAL_EXITO is None:
    print("GATE: FAIL — MDE_PREREG / UMBRAL_EXITO sin definir en config.py")
    print("      Rellena §7 del preregistro ANTES de interpretar lo de arriba.")
    sys.exit(1)

r = results["mfe_norm"]
pw = power_normal(MDE_PREREG, r["se"], ALPHA)
cruza_nulo = r["lo"] <= 0 <= r["hi"]

print(f"Potencia ante MDE_PREREG={MDE_PREREG}: {pw:.3f}")
if r["lo"] > UMBRAL_EXITO:
    veredicto = "EXITO — pasa a FASE 1"
elif cruza_nulo and pw < POWER_TARGET:
    veredicto = "NO CONCLUYENTE — ampliar n. NO es fallo de la hipotesis"
elif cruza_nulo and pw >= POWER_TARGET:
    veredicto = "REFUTACION — regla de paro §10.1. ALTO."
else:
    veredicto = "REVISAR MANUALMENTE contra §7"
print(f"VEREDICTO: {veredicto}")
print("=" * 60)

(OUT / "f0").mkdir(parents=True, exist_ok=True)
json.dump({"results": results, "power": pw, "veredicto": veredicto},
          open(OUT / "f0" / "test_cero.json", "w"), indent=2)
PYEOF

cd src && python f0_test_cero.py; cd ..
```

### GATE 0

| Veredicto | Acción |
|---|---|
| `EXITO` | continuar a FASE 1 |
| `NO CONCLUYENTE` | ampliar universo, repetir. Sin costo de evidencia |
| `REFUTACION` | **alto.** §10.1. La taxonomía es decorativa |

---

# FASE 1 — Trabajo gratis sobre las 6 sesiones

Requiere enganchar tu motor de libro. Define **una** interfaz y todo lo demás la consume:

```bash
cat > src/common/engine.py << 'PYEOF'
"""
ADAPTADOR — unico punto de contacto con tu replay MBO existente.
Implementa estas dos funciones contra tu codigo y no toques nada mas.
"""
from typing import Dict
import pandas as pd


def replay_features(session_date, contract, t_eval, t_start=None) -> Dict[str, float]:
    """Reconstruye el libro desde t_start (o snapshot) y devuelve las 8 features
    evaluadas EN t_eval. Prohibido tocar eventos posteriores a t_eval."""
    raise NotImplementedError("engancha aqui tu replay MBO")


def derive_mbp10(session_date, contract) -> pd.DataFrame:
    """MBP-10 derivado de tu replay MBO, para la reconciliacion externa."""
    raise NotImplementedError
PYEOF
```

## 1a — Perfilado de warm-up

El snapshot da **estado**, no **historia**. Cualquier feature con componente de duración está censurada por izquierda aunque el libro esté completo.

```bash
cat > src/f1a_warmup.py << 'PYEOF'
import json
import numpy as np, pandas as pd
from common.config import *
from common.engine import replay_features

SESSIONS = [("2022-04-05","NQM2"), ("2022-08-31","NQU2"), ("2023-05-18","NQM3"),
            ("2023-08-29","NQU3"), ("2024-05-02","NQM4"), ("2024-07-16","NQU4")]
STARTS = ["08:29:00","08:00:00","07:30:00","06:30:00","05:00:00","03:00:00", None]  # None = snapshot completo
EPS = 0.01

rows = []
for d, c in SESSIONS:
    t_eval = pd.Timestamp(f"{d} 08:31:30", tz=TZ)
    ref = replay_features(d, c, t_eval, t_start=None)
    for s in STARTS[:-1]:
        v = replay_features(d, c, t_eval, t_start=pd.Timestamp(f"{d} {s}", tz=TZ))
        for k in ref:
            denom = abs(ref[k]) if abs(ref[k]) > 1e-9 else 1.0
            rows.append(dict(date=d, feature=k, start=s,
                             rel_err=abs(v[k]-ref[k])/denom))

df = pd.DataFrame(rows)
piv = df.groupby(["feature","start"]).rel_err.max().unstack()
print(piv.round(4).to_string())

warm = {}
for f in piv.index:
    ok = [s for s in piv.columns if piv.loc[f, s] < EPS]
    warm[f] = min(ok) if ok else "NO SATURA"
print("\nWarm-up minimo por feature:")
for k, v in warm.items():
    print(f"  {k:35s} {v}")

fails = [k for k,v in warm.items() if v == "NO SATURA"]
print("\nGATE 1a:", "FAIL — " + ", ".join(fails) if fails else "PASS")
(OUT/"f1a").mkdir(parents=True, exist_ok=True)
json.dump(warm, open(OUT/"f1a"/"warmup.json","w"), indent=2, default=str)
PYEOF

cd src && python f1a_warmup.py; cd ..
```

**Salida operativa:** el warm-up más largo define desde dónde arranca todo replay posterior. Anótalo en §5.1 del preregistro. *Esto todavía puede cambiar §5.1 legítimamente — no has visto ningún outcome.*

## 1b — Nulo calibrado

Sin esto no sabes si un valor extremo en `t_burst` es extremo o es lo que hace el libro de NQ todo el día.

```bash
cat > src/f1b_null_calib.py << 'PYEOF'
import json
import numpy as np, pandas as pd
from common.config import *
from common.engine import replay_features

SESSIONS = [("2022-04-05","NQM2"), ("2022-08-31","NQU2"), ("2023-05-18","NQM3"),
            ("2023-08-29","NQU3"), ("2024-05-02","NQM4"), ("2024-07-16","NQU4")]
N_PSEUDO = 2000
rng = np.random.default_rng(SEED)

null_rows, real_rows = [], []
for d, c in SESSIONS:
    lo = pd.Timestamp(f"{d} 08:35:00", tz=TZ).value   # tras warm-up de 1a
    hi = pd.Timestamp(f"{d} 14:30:00", tz=TZ).value
    for _ in range(N_PSEUDO):
        t = pd.Timestamp(rng.integers(lo, hi), tz="UTC").tz_convert(TZ)
        f = replay_features(d, c, t)          # niveles arbitrarios, NO borde OR
        null_rows.append(dict(date=d, **f))
    t_burst = pd.Timestamp(f"{d} 08:31:30", tz=TZ)     # <-- tu t_burst real
    real_rows.append(dict(date=d, **replay_features(d, c, t_burst)))

null = pd.DataFrame(null_rows); real = pd.DataFrame(real_rows)
feats = [c for c in null.columns if c != "date"]

print(f"{'feature':35s} {'pctil medio':>12s} {'min':>7s} {'max':>7s}")
pct = {}
for f in feats:
    p = [(null.loc[null.date==r.date, f] < getattr(r, f)).mean()*100 for r in real.itertuples()]
    pct[f] = p
    print(f"{f:35s} {np.mean(p):12.1f} {min(p):7.1f} {max(p):7.1f}")

extremos = [f for f in feats if np.mean(pct[f]) > 95 or np.mean(pct[f]) < 5]
print(f"\nFeatures fuera del nulo: {extremos if extremos else 'NINGUNA'}")
print("GATE 1b: PASS (informativa — no bloquea)")
(OUT/"f1b").mkdir(parents=True, exist_ok=True)
null.to_parquet(OUT/"f1b"/"null_dist.parquet")
json.dump({k: list(map(float,v)) for k,v in pct.items()}, open(OUT/"f1b"/"percentiles.json","w"), indent=2)
PYEOF

cd src && python f1b_null_calib.py; cd ..
```

> n=6 aquí es diagnóstico de ingeniería, no evidencia. Ninguna feature "fuera del nulo" en 6 sesiones significa nada estadísticamente.

## 1c — Sensibilidad de umbrales

```bash
cat > src/f1c_sensitivity.py << 'PYEOF'
import itertools, json
import numpy as np, pandas as pd
from common.config import *
from common.engine import replay_features

BASE = dict(ratio=RATIO_IMBALANCE, vol=VOL_MIN_CELDA,
            niveles=NIVELES_APILADOS, dist=DIST_BORDE_TICKS)
PERT = [0.7, 0.85, 1.0, 1.15, 1.3]

rows = []
for param in BASE:
    for m in PERT:
        cfg = dict(BASE); cfg[param] = BASE[param] * m
        # TODO: recomputar el conjunto de eventos con cfg
        n_ev, jac = None, None   # <- enganchar detector
        rows.append(dict(param=param, mult=m, n_eventos=n_ev, jaccard_vs_base=jac))

df = pd.DataFrame(rows)
print(df.to_string(index=False))

frag = df[(df.mult.between(0.85,1.15)) & (df.jaccard_vs_base < 0.7)]
print("\nGATE 1c:", "FAIL — colapso ante perturbacion pequena en: "
      + ", ".join(frag.param.unique()) if len(frag) else "PASS")
(OUT/"f1c").mkdir(parents=True, exist_ok=True)
df.to_csv(OUT/"f1c"/"sensitivity.csv", index=False)
PYEOF
```

**GATE 1c en `FAIL` significa que el sobreajuste ya ocurrió en la especificación**, antes de ver un solo resultado. Se declara en §5.2 y se resuelve antes de continuar.

## 1d — Reconciliación externa

> "Reconciliación interna 100.0000%" compara el replay contra sí mismo. Esta es la que tiene poder.

**Costo adicional.** Requiere `mbp-10` y `ohlcv-1s` de Databento para las mismas 6 sesiones. `ohlcv-1s` es marginal; `mbp-10` no es cero. **Cotiza antes de descargar** — sigue aplicando tu regla de no descargar sin autorización explícita.

```bash
cat > src/f1d_reconcile.py << 'PYEOF'
import json
import pandas as pd, databento as db
from common.config import *
from common.engine import derive_mbp10

SESSIONS = [("2022-04-05","NQM2"), ("2022-08-31","NQU2"), ("2023-05-18","NQM3"),
            ("2023-08-29","NQU3"), ("2024-05-02","NQM4"), ("2024-07-16","NQU4")]

res = []
for d, c in SESSIONS:
    ref = db.DBNStore.from_file(DATA/"raw"/f"mbp10_{d}_{c}.dbn.zst").to_df()
    mine = derive_mbp10(d, c)
    j = ref.join(mine, how="inner", lsuffix="_ref", rsuffix="_mine")
    cols = [f"{s}_{lvl}" for lvl in range(3) for s in ("bid_px","ask_px","bid_sz","ask_sz")]
    mism = {k: float((j[f"{k}_ref"] != j[f"{k}_mine"]).mean()) for k in cols if f"{k}_ref" in j}
    res.append(dict(date=d, n=len(j), max_mismatch=max(mism.values()) if mism else None, **mism))

df = pd.DataFrame(res)
print(df.to_string(index=False))
worst = df.max_mismatch.max()
print(f"\nGATE 1d: {'PASS' if worst == 0 else f'FAIL — mismatch max {worst:.6%}'}")
(OUT/"f1d").mkdir(parents=True, exist_ok=True)
df.to_csv(OUT/"f1d"/"reconcile.csv", index=False)
PYEOF
```

GATE 1d en `FAIL` dispara la regla de paro §10.4.

---

# FASE 2 — Congelar

Solo con GATE 0 = `EXITO` y GATEs 1a/1c/1d = `PASS`.

```bash
# 1. Rellena los blancos: §2 endpoint, §4 etiqueta, §5.1 warm-up (de 1a), §7 los tres numeros
$EDITOR PREREGISTRO_AB_ORB_NQ.md

# 2. Verificar que no quedan blancos
grep -n '\\_\\_\\_\\_' PREREGISTRO_AB_ORB_NQ.md && echo ">>> QUEDAN BLANCOS — no congelar" || echo ">>> completo"

# 3. Congelar
sha256sum PREREGISTRO_AB_ORB_NQ.md | tee PREREGISTRO.sha256
git add -A
git commit -m "freeze: preregistro separacion A/B $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git tag -a prereg-ab-v1 -m "$(cat PREREGISTRO.sha256)"
git push --follow-tags
```

**A partir de este commit, cualquier cambio a §0 tabla-congelada se registra en §11 y consume presupuesto de iteración (§9). Presupuesto: 1.**

---

# FASE 3 — Censo

```bash
cat > src/f3_cotizar.py << 'PYEOF'
import databento as db
from common.config import *
c = db.Historical()
cost = c.metadata.get_cost(dataset="GLBX.MDP3", schema="mbo",
                           symbols=["NQ.c.0"], stype_in="continuous",
                           start="2022-01-01", end="2024-12-31")
print(f"Censo MBO 2022-2024: USD {cost:.2f}")
PYEOF

cd src && python f3_cotizar.py; cd ..
```

Muestreo **no selectivo**: toda sesión que cumpla el filtro de §3 entra. Nada elegido a mano.

Después: split purgado con embargo, hash del split, y **el test set no se abre hasta el final. Una vez.**

---

## Orden y costo

| Fase | Costo | Puede cerrar el programa |
|---|---|---|
| 0 | USD 0 | **sí** |
| 1a–1c | USD 0 | 1c sí |
| 1d | cotizar | sí (§10.4) |
| 2 | USD 0 | — |
| 3 | ~USD 180–220 | — |

Ejecuta 0 antes que nada. Es gratis y es el único que puede ahorrarte el resto.
