# -*- coding: utf-8 -*-
"""
08_analyze_cvd_at_entry.py

Analiza el Excel generado por el exporter version
"score-exporter-2026-06-11-x10-cvd-at-entry" o posterior.

Que hace:
  1. Valida el filtro de entrada Cvd_Pullback_Pct_AtEntry (SIN lookahead:
     se calcula solo con barras hasta la entrada) con estabilidad mensual
     y split temporal train/test.
  2. Simula la regla de salida anticipada: "salir al primer cambio de
     etiqueta intra-trade a 'Riesgo de reversion'" usando la columna
     CvdRisk_First_FavTicks (instrumentada en tiempo real, legitima).
  3. Simula parciales 50% a 1R + runner a 2R/3R usando MAE/MFE.

Uso:
    python 08_analyze_cvd_at_entry.py Score_indicator_results_updated.xlsx
"""

import sys

import numpy as np
import pandas as pd


def load(path):
    df = pd.read_excel(path, skiprows=2)
    df["fecha"] = pd.to_datetime(df["fecha"])
    t = df[df["Result_Label"].isin(["TP", "SL"])].copy().sort_values("fecha")
    t["pnl"] = pd.to_numeric(t["result TP SL BE"], errors="coerce")
    t["win"] = (t["Result_Label"] == "TP").astype(int)
    return t


def stats(g, name=""):
    n = len(g)
    if n == 0:
        return f"{name:42s} n=  0"
    wr = g["win"].mean() * 100
    gp = g.loc[g["pnl"] > 0, "pnl"].sum()
    gl = -g.loc[g["pnl"] < 0, "pnl"].sum()
    pf = gp / gl if gl > 0 else float("inf")
    return (f"{name:42s} n={n:3d} WR={wr:5.1f}% PF={pf:5.2f} "
            f"net={g['pnl'].sum():7.0f} ticks")


def seccion_1_filtro_at_entry(t):
    print("=" * 78)
    print("1) FILTRO DE ENTRADA: Cvd_Pullback_Pct_AtEntry (sin lookahead)")
    print("=" * 78)
    col = "Cvd_Pullback_Pct_AtEntry"
    if col not in t.columns or t[col].isna().all():
        print(f"  Columna {col} no encontrada o vacia.")
        print("  Re-ejecuta el replay con el exporter 2026-06-11 o posterior.")
        return

    t = t.copy()
    t["pct"] = pd.to_numeric(t[col], errors="coerce")

    print("\n-- WR por bins del pullback at-entry --")
    bins = [-0.01, 0.10, 0.25, 0.50, 0.75, 1.01]
    for k, g in t.groupby(pd.cut(t["pct"], bins), observed=True):
        print(stats(g, str(k)))

    # Umbral candidato: solo operar con pullback bajo (CVD cerca de su
    # extremo a favor). NO optimices este umbral al decimal: usa los
    # cortes naturales de la etiqueta (0.25 / 0.50).
    for thr in (0.25, 0.50):
        f = t[t["pct"] <= thr]
        x = t[t["pct"] > thr]
        print(f"\n-- Umbral <= {thr} --")
        print(stats(f, "  PASA filtro"))
        print(stats(x, "  EXCLUIDO"))

        print("  Estabilidad mensual del filtro:")
        meses_perdedores = 0
        for m, g in f.groupby(f["fecha"].dt.to_period("M")):
            linea = stats(g, f"    {m}")
            print(linea)
            if g["pnl"].sum() < 0:
                meses_perdedores += 1
        print(f"  Meses perdedores con filtro: {meses_perdedores}")

        fechas = t["fecha"].sort_values()
        corte = fechas.iloc[int(len(fechas) * 0.7)]
        tr, te = f[f["fecha"] < corte], f[f["fecha"] >= corte]
        print(f"  Split temporal (corte {corte.date()}):")
        print(stats(tr, "    train (70%)"))
        print(stats(te, "    test  (30%)"))


def seccion_2_salida_por_riesgo(t):
    print("\n" + "=" * 78)
    print("2) SIMULACION: salir al primer 'Riesgo de reversion' intra-trade")
    print("=" * 78)
    col = "CvdRisk_First_FavTicks"
    if col not in t.columns or t[col].isna().all():
        print(f"  Columna {col} no encontrada o vacia. Requiere replay nuevo.")
        return

    t = t.copy()
    t["risk_bar"] = pd.to_numeric(t.get("CvdRisk_First_BarOffset"), errors="coerce")
    t["risk_fav"] = pd.to_numeric(t[col], errors="coerce")

    # PnL simulado: si hubo transicion a Riesgo antes del cierre, se asume
    # salida a mercado en ese momento (favorable ticks con signo);
    # si no hubo transicion, el trade queda igual.
    tuvo = t["risk_bar"].notna() & (t["risk_bar"] >= 0)
    t["pnl_sim"] = np.where(tuvo, t["risk_fav"], t["pnl"])

    print(stats(t, "Sistema actual"))
    sim = t.copy()
    sim["pnl"] = sim["pnl_sim"]
    sim["win"] = (sim["pnl"] > 0).astype(int)
    print(stats(sim, "Con salida anticipada por Riesgo CVD"))
    print(f"\nTrades con transicion a Riesgo: {tuvo.sum()} de {len(t)}")
    if tuvo.any():
        sub = t[tuvo]
        print(stats(sub, "  Esos trades, resultado real"))
        print(f"  Resultado simulado saliendo en la transicion: "
              f"{sub['risk_fav'].sum():.0f} ticks vs real {sub['pnl'].sum():.0f}")
    print("\nNota: la simulacion asume fill al cierre de la barra de la")
    print("transicion; en vivo habria slippage. Exige un margen amplio antes")
    print("de activar EnableCvdRiskManagementForNormalSpeed.")


def seccion_3_parciales(t):
    print("\n" + "=" * 78)
    print("3) SIMULACION: parcial 50% a 1R + runner (usando MAE/MFE)")
    print("=" * 78)
    req = {"MFE_ticks", "MAE_ticks", "TP_ticks", "SL_ticks"}
    if not req.issubset(t.columns):
        print("  Faltan columnas MAE/MFE/TP/SL.")
        return

    t = t.copy()
    for c in req:
        t[c] = pd.to_numeric(t[c], errors="coerce")
    t = t.dropna(subset=list(req))
    t = t[t["TP_ticks"] > 0]

    print(stats(t, "Sistema actual (1:1 completo)"))

    for runner_mult in (2, 3):
        # 50% sale a 1R (TP actual). El resto busca runner_mult * R con
        # stop en BE tras el parcial. Aproximacion con MAE/MFE:
        #   - MFE >= 1R  -> parcial cobrado (+0.5R)
        #   - runner: MFE >= runner_mult*R -> +0.5*runner_mult*R
        #             si no, BE (0) en la mitad restante
        #   - MFE < 1R -> trade completo a SL (-1R) [conservador: en la
        #     realidad algunos cerrarian TIME_OVER mejor]
        r = t["TP_ticks"]
        hit_1r = t["MFE_ticks"] >= r
        hit_runner = t["MFE_ticks"] >= runner_mult * r
        pnl = np.where(
            hit_1r,
            0.5 * r + np.where(hit_runner, 0.5 * runner_mult * r, 0.0),
            -t["SL_ticks"].values,
        )
        sim = t.copy()
        sim["pnl"] = pnl
        sim["win"] = (sim["pnl"] > 0).astype(int)
        print(stats(sim, f"Parcial 50% a 1R + runner a {runner_mult}R (BE)"))

    print("\nNota: aproximacion optimista para el runner (no modela si el BE")
    print("se toca antes de alcanzar el objetivo cuando MFE >= objetivo).")
    print("Si algun esquema gana aqui, el siguiente paso es implementarlo en")
    print("el trade manager y validarlo con replay, no asumirlo.")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "Score_indicator_results_updated.xlsx"
    t = load(path)
    print(f"Archivo: {path} | trades validos: {len(t)} | "
          f"{t['fecha'].min().date()} -> {t['fecha'].max().date()}\n")
    print(stats(t, "BASELINE (por contrato)"))
    if "Trade_Contracts" in t.columns:
        c = pd.to_numeric(t["Trade_Contracts"], errors="coerce").fillna(1)
        if (c > 1).any():
            w = t.copy()
            w["pnl"] = w["pnl"] * c
            print(stats(w, "PONDERADO por Trade_Contracts"))
    print()
    seccion_1_filtro_at_entry(t)
    seccion_2_salida_por_riesgo(t)
    seccion_3_parciales(t)


if __name__ == "__main__":
    main()
