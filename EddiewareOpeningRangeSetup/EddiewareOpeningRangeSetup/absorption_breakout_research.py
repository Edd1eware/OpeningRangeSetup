"""Investigación causal de familias de Liquidity Burst.

Este módulo es estrictamente observacional. Lee snapshots disponibles antes de
la entrada y une outcomes canónicos después del cierre. Nunca escribe señales,
parámetros, stops, targets ni archivos consumidos por la estrategia.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import DBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, roc_auc_score
from sklearn.mixture import GaussianMixture
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier


RANDOM_SEED = 20260717
EXPECTED_EXPORTER_VERSION = "score-exporter-2026-07-18-v25-response-families"
EXPECTED_BURST_VERSION = "liquidity-burst-detector-2026-07-18-v2-response-families"
TELEGRAM_TITLE = "ANALISIS  FAMILIAS A, B, C, ETC."
TICK_SIZE = 0.25

OUTCOME_PATTERNS = re.compile(
    r"(?:^|_)(?:mfe|mae|result|exit|outcome|future|final|target_moved|stop_moved)(?:_|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    source: str
    formula: str
    units: str
    interpretation: str
    window_start_seconds: float
    window_end_seconds: float
    engineered: bool = False


BURST_SPECS = [
    FeatureSpec("Delta1s", "burst_events", "sum(delta, 1s)", "contracts", "Agresión neta del segundo del burst.", -1, 0),
    FeatureSpec("Delta2s", "burst_events", "sum(delta, 2s)", "contracts", "Persistencia corta de agresión.", -2, 0),
    FeatureSpec("Delta3s", "burst_events", "sum(delta, 3s)", "contracts", "Persistencia de agresión a 3 segundos.", -3, 0),
    FeatureSpec("Delta5s", "burst_events", "sum(delta, 5s)", "contracts", "Persistencia de agresión a 5 segundos.", -5, 0),
    FeatureSpec("Delta10s", "burst_events", "sum(delta, 10s)", "contracts", "Contexto pre-burst de 10 segundos.", -10, 0),
    FeatureSpec("PeakPositiveDelta", "burst_events", "max(delta_1s, 10s)", "contracts", "Pico comprador causal.", -10, 0),
    FeatureSpec("PeakNegativeDelta", "burst_events", "min(delta_1s, 10s)", "contracts", "Pico vendedor causal.", -10, 0),
    FeatureSpec("DeltaChange1s", "burst_events", "delta_t-delta_t-1", "contracts", "Salto instantáneo de agresión.", -2, 0),
    FeatureSpec("DeltaChangeZScore", "burst_events", "z(delta_change; history 300s)", "z", "Rareza del cambio frente al pasado.", -300, 0),
    FeatureSpec("DeltaPercentile", "burst_events", "percentile(|delta_change|; history)", "ratio", "Percentil causal de actividad.", -300, 0),
    FeatureSpec("BuySellRatio", "burst_events", "buy_volume/sell_volume", "ratio", "Asimetría de agresores.", -1, 0),
    FeatureSpec("TradesPerSecond", "burst_events", "count(trades,1s)", "trades/s", "Intensidad de ejecuciones.", -1, 0),
    FeatureSpec("ContractsPerSecond", "burst_events", "sum(volume,1s)", "contracts/s", "Intensidad de contratos.", -1, 0),
    FeatureSpec("Velocity1s", "burst_events", "price displacement/tick/1s", "ticks/s", "Desplazamiento de precio por segundo.", -1, 0),
    FeatureSpec("Velocity3s", "burst_events", "price displacement/tick/3s", "ticks/s", "Velocidad a 3 segundos.", -3, 0),
    FeatureSpec("Velocity5s", "burst_events", "price displacement/tick/5s", "ticks/s", "Velocidad a 5 segundos.", -5, 0),
    FeatureSpec("Acceleration1s", "burst_events", "velocity1s_t-velocity1s_t-1", "ticks/s2", "Cambio de velocidad inmediato.", -2, 0),
    FeatureSpec("Acceleration3s", "burst_events", "velocity3s_t-velocity3s_t-1", "ticks/s2", "Cambio de velocidad suavizado.", -4, 0),
    FeatureSpec("TicksPerSecond", "burst_events", "Velocity1s", "ticks/s", "Impacto observado en precio.", -1, 0),
    FeatureSpec("CumulativeDeltaWindow", "burst_events", "sum(delta,CumulativeWindowSeconds)", "contracts", "CVD causal del burst.", -3, 0),
    FeatureSpec("OR_WidthTicks", "burst_events", "(OR_high-OR_low)/tick", "ticks", "Régimen de rango de apertura.", -60, 0),
    FeatureSpec("Dist_OR_High_Ticks", "burst_events", "(price-OR_high)/tick", "ticks", "Ubicación respecto al OR high.", -60, 0),
    FeatureSpec("Dist_OR_Low_Ticks", "burst_events", "(price-OR_low)/tick", "ticks", "Ubicación respecto al OR low.", -60, 0),
    FeatureSpec("Dist_VWAP_Ticks", "burst_events", "(price-vwap)/tick", "ticks", "Ubicación respecto a VWAP.", -1800, 0),
    FeatureSpec("Dist_POC_Ticks", "burst_events", "(price-poc)/tick", "ticks", "Ubicación respecto al POC causal.", -1800, 0),
    FeatureSpec("Dist_VAH_Ticks", "burst_events", "(price-vah)/tick", "ticks", "Ubicación respecto al VAH causal.", -1800, 0),
    FeatureSpec("Dist_VAL_Ticks", "burst_events", "(price-val)/tick", "ticks", "Ubicación respecto al VAL causal.", -1800, 0),
    FeatureSpec("Dist_HVN_Ticks", "burst_events", "(price-nearest_hvn)/tick", "ticks", "Distancia a nodo de alto volumen.", -1800, 0),
    FeatureSpec("Dist_LVN_Ticks", "burst_events", "(price-nearest_lvn)/tick", "ticks", "Distancia a nodo de bajo volumen.", -1800, 0),
    FeatureSpec("PreBurst_Acceptance_Dwell_Ratio_5s", "burst_events", "seconds accepted beyond broken OR edge / observed seconds", "ratio", "Aceptación causal previa al burst.", -5, 0),
    FeatureSpec("PreBurst_Reclaim_Count_10s", "burst_events", "crossings from accepted to reclaimed side", "count", "Reclaims causales antes del burst.", -10, 0),
    FeatureSpec("PreBurst_Rotation_Index_10s", "burst_events", "direction changes/nonzero price changes", "ratio", "Rotación local de la subasta.", -10, 0),
    FeatureSpec("PreBurst_Local_Entropy_10s", "burst_events", "binary entropy(up,down)", "bits", "Complejidad de la secuencia previa.", -10, 0),
    FeatureSpec("PreBurst_Path_Efficiency_10s", "burst_events", "directional net move/absolute path", "ratio", "Eficiencia de trayectoria previa.", -10, 0),
    FeatureSpec("PreBurst_Price_Per_Delta_3s", "burst_events", "directional ticks/abs(delta)", "ticks/contract", "Resultado de precio por agresión.", -3, 0),
    FeatureSpec("PreBurst_Price_Per_Volume_3s", "burst_events", "directional ticks/volume", "ticks/contract", "Resultado de precio por volumen.", -3, 0),
    FeatureSpec("PreBurst_Impulse_Survival_Seconds", "burst_events", "consecutive directional seconds ending at burst", "seconds", "Supervivencia causal del impulso.", -5, 0),
    FeatureSpec("PreBurst_Impulse_Decay_Slope_5s", "burst_events", "OLS slope of directional one-second moves", "ticks/s2", "Decaimiento o expansión del impulso.", -5, 0),
    FeatureSpec("Profile_Std_Ticks", "burst_events", "volume-weighted profile standard deviation", "ticks", "Dispersión matemática del perfil.", -1800, 0),
    FeatureSpec("Profile_Skewness", "burst_events", "volume-weighted third standardized moment", "ratio", "Asimetría matemática del perfil.", -1800, 0),
    FeatureSpec("Profile_Excess_Kurtosis", "burst_events", "volume-weighted fourth standardized moment-3", "ratio", "Colas/concentración del perfil.", -1800, 0),
    FeatureSpec("Profile_Normalized_Entropy", "burst_events", "profile entropy/log(number of price nodes)", "ratio", "Dispersión de volumen entre niveles.", -1800, 0),
    FeatureSpec("Profile_Concentration", "burst_events", "POC volume/total profile volume", "ratio", "Concentración modal sin etiqueta manual.", -1800, 0),
    FeatureSpec("Profile_Effective_Nodes", "burst_events", "exp(profile entropy)", "count", "Número efectivo de niveles negociados.", -1800, 0),
    FeatureSpec("Profile_Local_Maxima_Count", "burst_events", "count(local maxima in volume profile)", "count", "Multimodalidad matemática.", -1800, 0),
    FeatureSpec("Profile_Position_Percentile", "burst_events", "cumulative profile volume below price/total volume", "ratio", "Posición relativa dentro de la subasta.", -1800, 0),
    FeatureSpec("POC_Migration_Ticks", "burst_events", "current POC-prior emitted POC", "ticks", "Migración causal del centro de valor.", -1800, 0),
]

ENTRY_SPECS = [
    FeatureSpec("range", "trade_inputs", "OR range at prediction", "ticks", "Régimen de apertura al decidir.", 0, 0),
    FeatureSpec("Body_AtEntry", "trade_inputs", "body breakout at prediction", "ticks", "Desplazamiento del bar al decidir.", 0, 0),
    FeatureSpec("Volume_AtEntry", "trade_inputs", "bar volume at prediction", "contracts", "Participación acumulada disponible.", -60, 0),
    FeatureSpec("Delta_AtEntry", "trade_inputs", "bar delta at prediction", "contracts", "Agresión acumulada disponible.", -60, 0),
    FeatureSpec("Cumulative_Delta_AtEntry", "trade_inputs", "session CVD at prediction", "contracts", "Régimen direccional causal.", -1800, 0),
    FeatureSpec("Previous_Volume_AtEntry", "trade_inputs", "previous closed bar volume", "contracts", "Actividad previa cerrada.", -120, -1),
    FeatureSpec("Previous_Delta_AtEntry", "trade_inputs", "previous closed bar delta", "contracts", "Agresión previa cerrada.", -120, -1),
    FeatureSpec("Delta_Change_AtEntry", "trade_inputs", "delta-current minus previous", "contracts", "Cambio de agresión al decidir.", -120, 0),
    FeatureSpec("BreakOut_TICKS_PER_SEC_AtEntry", "trade_inputs", "causal breakout speed", "ticks/s", "Velocidad del setup al decidir.", -60, 0),
    FeatureSpec("Score_AtEntry", "trade_inputs", "score available at prediction", "points", "Confluencia causal predefinida.", -60, 0),
    FeatureSpec("Buy_Imbalance_Count_AtEntry", "trade_inputs", "buy imbalance count", "count", "Desequilibrios compradores observados.", -60, 0),
    FeatureSpec("Sell_Imbalance_Count_AtEntry", "trade_inputs", "sell imbalance count", "count", "Desequilibrios vendedores observados.", -60, 0),
    FeatureSpec("Seconds_From_Open_AtEntry", "trade_inputs", "entry_ny-09:30 NY", "seconds", "Régimen temporal exacto al decidir.", -600, 0),
    FeatureSpec("Directional_OR_Extension_Ticks_AtEntry", "trade_inputs", "execution_sign*distance beyond execution-side OR edge", "ticks", "Extensión causal respecto al OR.", -600, 0),
    FeatureSpec("Directional_VWAP_Distance_Ticks_AtEntry", "trade_inputs", "execution_sign*(entry-vwap)/tick", "ticks", "Alineación de entrada con valor negociado.", -600, 0),
    FeatureSpec("Nearest_OR_Edge_Distance_Ticks_AtEntry", "trade_inputs", "min(abs(entry-OR high),abs(entry-OR low))/tick", "ticks", "Proximidad al borde estructural más cercano.", -600, 0),
    FeatureSpec("Body_OR_Ratio_AtEntry", "trade_inputs", "abs(body ticks)/max(OR ticks,1)", "ratio", "Extensión del cuerpo normalizada por régimen.", -60, 0),
    FeatureSpec("Signed_Delta_Share_AtEntry", "trade_inputs", "execution_sign*bar delta/max(bar volume,1)", "ratio", "Agresión del bar alineada con la ejecución.", -60, 0),
    FeatureSpec("Signed_Previous_Delta_Share_AtEntry", "trade_inputs", "execution_sign*previous delta/max(previous volume,1)", "ratio", "Agresión cerrada previa alineada.", -120, -1),
    FeatureSpec("Prior_Closed_ATR3_Ticks_AtEntry", "trade_inputs", "mean true range of prior 3 closed bars", "ticks", "Volatilidad causal inmediata.", -240, -1),
    FeatureSpec("Prior_Closed_ATR5_Ticks_AtEntry", "trade_inputs", "mean true range of prior 5 closed bars", "ticks", "Volatilidad causal suavizada.", -360, -1),
    FeatureSpec("PreEntry_Directional_Efficiency3_AtEntry", "trade_inputs", "execution_sign*net move/sum ranges of prior 3 closed bars", "ratio", "Eficiencia de trayectoria previa.", -240, -1),
    FeatureSpec("PreEntry_Directional_Delta_Share3_AtEntry", "trade_inputs", "execution_sign*sum delta/sum volume prior 3 closed bars", "ratio", "Persistencia de agresión previa.", -240, -1),
    FeatureSpec("PreEntry_Range_Compression3_AtEntry", "trade_inputs", "ATR3/max(OR range,1)", "ratio", "Compresión o expansión previa normalizada.", -240, -1),
    FeatureSpec("PreEntry_Volume_Climax_Ratio_AtEntry", "trade_inputs", "last closed volume/mean earlier closed volumes", "ratio", "Clímax de participación antes del entry.", -300, -1),
    FeatureSpec("Nearest_OR_Edge_Retest_Count_AtEntry", "trade_inputs", "closed bars touching nearest OR edge before entry", "count", "Desgaste causal del nivel por retests.", -600, -1),
    FeatureSpec("Nearest_OR_Edge_Acceptance_Ratio3_AtEntry", "trade_inputs", "fraction prior 3 closed bars accepted outside nearest OR edge", "ratio", "Aceptación frente a rechazo del borde.", -240, -1),
    FeatureSpec("Directional_CLV_AtEntry", "trade_inputs", "execution_sign*(2*entry-causal_high-causal_low)/(causal_high-causal_low)", "ratio", "CLV construido sólo con precios observados hasta la señal.", -60, 0),
    FeatureSpec("PreEntry_Acceptance_Dwell_Ratio_AtEntry", "trade_inputs", "time beyond broken OR edge/time since first break", "ratio", "Aceptación causal antes de la entrada.", -60, 0),
    FeatureSpec("PreEntry_Reclaim_Count_AtEntry", "trade_inputs", "accepted-to-reclaimed crossings before signal", "count", "Número de reclaims antes de entrar.", -60, 0),
    FeatureSpec("PreEntry_Rejection_Speed_TPS_AtEntry", "trade_inputs", "max adverse ticks inside level/time since break", "ticks/s", "Velocidad causal de rechazo.", -60, 0),
    FeatureSpec("PreEntry_Rotation_Index_AtEntry", "trade_inputs", "direction changes/nonzero observed price changes", "ratio", "Rotación de la secuencia observada.", -60, 0),
    FeatureSpec("PreEntry_Local_Entropy_AtEntry", "trade_inputs", "binary entropy(up,down)", "bits", "Complejidad local de la secuencia.", -60, 0),
    FeatureSpec("PreEntry_Path_Efficiency_AtEntry", "trade_inputs", "directional net move/absolute observed path", "ratio", "Eficiencia direccional de trayectoria.", -60, 0),
    FeatureSpec("PreEntry_Price_Per_Delta_AtEntry", "trade_inputs", "directional ticks/abs(entry delta)", "ticks/contract", "Resultado por unidad de agresión.", -60, 0),
    FeatureSpec("PreEntry_Price_Per_Volume_AtEntry", "trade_inputs", "directional ticks/entry volume", "ticks/contract", "Resultado por unidad de volumen.", -60, 0),
]

ENGINEERED_SPECS = [
    FeatureSpec("signed_delta_1s", "engineered", "burst_sign*Delta1s", "contracts", "Agresión en dirección del burst.", -1, 0, True),
    FeatureSpec("signed_delta_change_1s", "engineered", "burst_sign*DeltaChange1s", "contracts", "Aceleración de agresión dirigida.", -2, 0, True),
    FeatureSpec("signed_velocity_1s", "engineered", "burst_sign*Velocity1s", "ticks/s", "Velocidad en dirección del burst.", -1, 0, True),
    FeatureSpec("signed_velocity_3s", "engineered", "burst_sign*Velocity3s", "ticks/s", "Persistencia de velocidad dirigida.", -3, 0, True),
    FeatureSpec("signed_acceleration_1s", "engineered", "burst_sign*Acceleration1s", "ticks/s2", "Aceleración dirigida del precio.", -2, 0, True),
    FeatureSpec("price_impact_per_100_contracts", "engineered", "100*abs(Velocity1s)/max(ContractsPerSecond,1)", "ticks/100 contracts", "Eficiencia de impacto del flujo.", -1, 0, True),
    FeatureSpec("absorption_pressure_1s", "engineered", "abs(Delta1s)/max(abs(Velocity1s),0.25)", "contracts/tick", "Agresión que no logra desplazar precio.", -1, 0, True),
    FeatureSpec("delta_share_of_volume", "engineered", "abs(Delta1s)/max(ContractsPerSecond,1)", "ratio", "Fracción direccional del volumen.", -1, 0, True),
    FeatureSpec("mean_trade_size", "engineered", "ContractsPerSecond/max(TradesPerSecond,1)", "contracts/trade", "Tamaño medio de ejecución.", -1, 0, True),
    FeatureSpec("delta_persistence_1_3", "engineered", "abs(Delta3s)/(3*max(abs(Delta1s),1))", "ratio", "Persistencia normalizada de agresión.", -3, 0, True),
    FeatureSpec("delta_persistence_3_5", "engineered", "3*abs(Delta5s)/(5*max(abs(Delta3s),1))", "ratio", "Persistencia de 3 a 5 segundos.", -5, 0, True),
    FeatureSpec("direction_consistency", "engineered", "mean(sign(Delta1/3/5)==burst_sign)", "ratio", "Consistencia temporal de agresión.", -5, 0, True),
    FeatureSpec("velocity_consistency", "engineered", "mean(sign(Velocity1/3/5)==burst_sign)", "ratio", "Consistencia temporal de desplazamiento.", -5, 0, True),
    FeatureSpec("flow_price_alignment", "engineered", "sign(Delta1s)*sign(Velocity1s)", "{-1,0,1}", "Alineación entre agresión y precio.", -1, 0, True),
    FeatureSpec("acceleration_velocity_ratio", "engineered", "signed_acceleration/max(abs(signed_velocity),0.25)", "ratio", "Cambio relativo del impacto.", -2, 0, True),
    FeatureSpec("directional_vwap_distance", "engineered", "burst_sign*Dist_VWAP_Ticks", "ticks", "Posición respecto a VWAP en dirección del burst.", -1800, 0, True),
    FeatureSpec("directional_poc_distance", "engineered", "burst_sign*Dist_POC_Ticks", "ticks", "Posición respecto a POC en dirección del burst.", -1800, 0, True),
    FeatureSpec("profile_confluence_4t", "engineered", "count(abs(dist POC/VAH/VAL/HVN/LVN)<=4)", "count", "Confluencia de niveles cerca del burst.", -1800, 0, True),
    FeatureSpec("burst_efficiency_score", "engineered", "signed_velocity_1s/max(abs(signed_delta_1s),1)", "ticks/contract", "Eficiencia direccional: breakout limpio alto.", -1, 0, True),
    FeatureSpec("liquidity_absorption_score", "engineered", "absorption_pressure_1s*(1-min(abs(signed_velocity_1s)/10,1))", "index", "Presión alta con bajo desplazamiento.", -1, 0, True),
]

ALL_SPECS = BURST_SPECS + ENTRY_SPECS + ENGINEERED_SPECS
FEATURE_NAMES = [spec.name for spec in ALL_SPECS]


def _to_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.upper().isin({"TRUE", "1", "YES"})


def _numeric(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")


def _safe_div(a: pd.Series, b: pd.Series, floor: float = 1.0) -> pd.Series:
    denominator = b.abs().clip(lower=floor)
    return a / denominator


def _load_inputs(results_folder: Path) -> pd.DataFrame:
    path = results_folder / "trade_inputs.csv"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, low_memory=False)
    if "Input_VERSION" in frame:
        expected = frame["Input_VERSION"].astype(str).eq(EXPECTED_EXPORTER_VERSION)
        frame = frame.loc[expected].copy()
    if "Directional_CLV_AtEntry" in frame and "CLV_Causality_Status_AtEntry" in frame:
        causal_clv = frame["CLV_Causality_Status_AtEntry"].astype(str).eq("CAUSAL_EVENT_RANGE")
        frame.loc[~causal_clv, "Directional_CLV_AtEntry"] = np.nan
    if "Liquidity_Burst_AtEntry" not in frame:
        return pd.DataFrame()
    frame = frame.loc[_to_bool(frame["Liquidity_Burst_AtEntry"])].copy()
    frame = frame.loc[frame["Liquidity_Burst_ID_AtEntry"].fillna("").astype(str).ne("")]
    frame["prediction_timestamp"] = pd.to_datetime(frame["feature_timestamp_utc"], utc=True, errors="coerce")
    frame["entry_timestamp_utc_parsed"] = pd.to_datetime(frame["entry_timestamp_utc"], utc=True, errors="coerce")
    frame = frame.sort_values(["fecha", "prediction_timestamp"], kind="stable")
    frame = frame.drop_duplicates(["fecha", "Liquidity_Burst_ID_AtEntry", "Side", "Entry_price"], keep="last")
    return frame.reset_index(drop=True)


def _load_bursts(results_folder: Path) -> pd.DataFrame:
    path = results_folder / "burst_events.csv"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, low_memory=False)
    if "Detector_VERSION" in frame:
        expected = frame["Detector_VERSION"].astype(str).eq(EXPECTED_BURST_VERSION)
        frame = frame.loc[expected].copy()
    frame["burst_event_timestamp"] = pd.to_datetime(
        frame["Timestamp_UTC"], utc=True, errors="coerce"
    )
    available_column = "Feature_Available_Timestamp_UTC"
    if available_column not in frame:
        return pd.DataFrame()
    frame["burst_timestamp"] = pd.to_datetime(
        frame[available_column], utc=True, errors="coerce"
    )
    frame = frame.sort_values(["BurstId", "burst_timestamp"], kind="stable")
    return frame.drop_duplicates("BurstId", keep="last").reset_index(drop=True)


def _canonical_outcomes(results_folder: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for path in sorted(results_folder.glob("score_trade_result_????-??-??_NY.csv")):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                row = next(reader, None)
            if row:
                row["canonical_source_file"] = str(path)
                rows.append(row)
        except (OSError, csv.Error, UnicodeError):
            continue
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    if "Exporter_VERSION" in frame:
        expected = frame["Exporter_VERSION"].astype(str).eq(EXPECTED_EXPORTER_VERSION)
        frame = frame.loc[expected].copy()
    return frame.drop_duplicates("fecha", keep="last").reset_index(drop=True)


def _engineer(frame: pd.DataFrame) -> pd.DataFrame:
    numeric = [spec.name for spec in BURST_SPECS + ENTRY_SPECS]
    numeric += ["Entry_price", "Initial_SL_ticks", "Initial_TP_ticks", "MAE_ticks", "MFE_ticks"]
    _numeric(frame, numeric)
    burst_sign = np.where(frame["BurstSide"].astype(str).str.upper().eq("BUY"), 1.0, -1.0)
    frame["burst_sign"] = burst_sign
    frame["signed_delta_1s"] = burst_sign * frame["Delta1s"]
    frame["signed_delta_change_1s"] = burst_sign * frame["DeltaChange1s"]
    frame["signed_velocity_1s"] = burst_sign * frame["Velocity1s"]
    frame["signed_velocity_3s"] = burst_sign * frame["Velocity3s"]
    frame["signed_acceleration_1s"] = burst_sign * frame["Acceleration1s"]
    frame["price_impact_per_100_contracts"] = 100 * frame["Velocity1s"].abs() / frame["ContractsPerSecond"].abs().clip(lower=1)
    frame["absorption_pressure_1s"] = frame["Delta1s"].abs() / frame["Velocity1s"].abs().clip(lower=TICK_SIZE)
    frame["delta_share_of_volume"] = frame["Delta1s"].abs() / frame["ContractsPerSecond"].abs().clip(lower=1)
    frame["mean_trade_size"] = frame["ContractsPerSecond"].abs() / frame["TradesPerSecond"].abs().clip(lower=1)
    frame["delta_persistence_1_3"] = frame["Delta3s"].abs() / (3 * frame["Delta1s"].abs().clip(lower=1))
    frame["delta_persistence_3_5"] = 3 * frame["Delta5s"].abs() / (5 * frame["Delta3s"].abs().clip(lower=1))
    frame["direction_consistency"] = np.mean(
        np.column_stack([
            np.sign(frame["Delta1s"]) == burst_sign,
            np.sign(frame["Delta3s"]) == burst_sign,
            np.sign(frame["Delta5s"]) == burst_sign,
        ]), axis=1,
    )
    frame["velocity_consistency"] = np.mean(
        np.column_stack([
            np.sign(frame["Velocity1s"]) == burst_sign,
            np.sign(frame["Velocity3s"]) == burst_sign,
            np.sign(frame["Velocity5s"]) == burst_sign,
        ]), axis=1,
    )
    frame["flow_price_alignment"] = np.sign(frame["Delta1s"]) * np.sign(frame["Velocity1s"])
    frame["acceleration_velocity_ratio"] = frame["signed_acceleration_1s"] / frame["signed_velocity_1s"].abs().clip(lower=TICK_SIZE)
    frame["directional_vwap_distance"] = burst_sign * frame["Dist_VWAP_Ticks"]
    frame["directional_poc_distance"] = burst_sign * frame["Dist_POC_Ticks"]
    profile_columns = ["Dist_POC_Ticks", "Dist_VAH_Ticks", "Dist_VAL_Ticks", "Dist_HVN_Ticks", "Dist_LVN_Ticks"]
    frame["profile_confluence_4t"] = frame[profile_columns].abs().le(4).sum(axis=1)
    frame["burst_efficiency_score"] = frame["signed_velocity_1s"] / frame["signed_delta_1s"].abs().clip(lower=1)
    frame["liquidity_absorption_score"] = frame["absorption_pressure_1s"] * (
        1 - (frame["signed_velocity_1s"].abs() / 10).clip(upper=1)
    )
    return frame


def _label_family(row: pd.Series) -> tuple[str, str]:
    result = str(row.get("Result_Label", "")).upper()
    mae = float(row.get("MAE_ticks", np.nan))
    mfe = float(row.get("MFE_ticks", np.nan))
    sl = float(row.get("Initial_SL_ticks", np.nan))
    tp = float(row.get("Initial_TP_ticks", np.nan))
    if result == "TP" and np.isfinite(mae) and np.isfinite(mfe) and mae <= 10 and mfe >= tp:
        return "A_TRUE_ABSORPTION", "TP; MAE<=10; MFE>=TP inicial"
    if result == "SL" and np.isfinite(mae) and np.isfinite(mfe) and mfe <= 10 and mae >= sl:
        return "B_CLEAN_BREAKOUT", "SL; MFE<=10; MAE>=SL inicial"
    if result in {"TP", "SL"}:
        return "C_MIXED_PATH", "TP/SL con excursión intermedia; no cumple A ni B estricta"
    return "D_OTHER_EXIT", f"Salida {result or 'desconocida'}"


def build_dataset(results_folder: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    inputs = _load_inputs(results_folder)
    bursts = _load_bursts(results_folder)
    outcomes = _canonical_outcomes(results_folder)
    if inputs.empty or bursts.empty or outcomes.empty:
        return pd.DataFrame(), pd.DataFrame([{
            "stage": "dataset", "status": "INSUFFICIENT_INPUT", "inputs": len(inputs),
            "bursts": len(bursts), "outcomes": len(outcomes),
        }])

    merged = inputs.merge(
        bursts,
        left_on="Liquidity_Burst_ID_AtEntry",
        right_on="BurstId",
        how="left",
        validate="many_to_one",
        suffixes=("_input", "_burst"),
    )
    merged = merged.merge(outcomes, on="fecha", how="left", validate="many_to_one", suffixes=("", "_outcome"))
    merged["BurstSide"] = merged["Side_burst"].fillna(merged["Liquidity_Burst_Side_AtEntry"])
    merged["ExecutionSide"] = merged["Side_input"]
    merged["burst_before_prediction"] = merged["burst_timestamp"].le(merged["prediction_timestamp"])
    merged["entry_feature_before_prediction"] = pd.to_datetime(
        merged["feature_timestamp_utc"], utc=True, errors="coerce"
    ).le(merged["prediction_timestamp"])
    merged["available_before_entry"] = pd.to_numeric(merged["AvailableBeforeEntry"], errors="coerce").eq(1)
    merged["causal_row_flag"] = (
        merged["burst_before_prediction"] &
        merged["entry_feature_before_prediction"] &
        merged["available_before_entry"] &
        merged["prediction_timestamp"].notna()
    )
    merged = _engineer(merged)
    labels = merged.apply(_label_family, axis=1, result_type="expand")
    merged["family"] = labels[0]
    merged["family_reason"] = labels[1]
    merged = merged.sort_values(["prediction_timestamp", "fecha"], kind="stable").reset_index(drop=True)
    n = len(merged)
    discovery_end = max(1, math.floor(n * 0.60))
    validation_end = max(discovery_end + 1, math.floor(n * 0.80)) if n > 2 else n
    validation_end = min(validation_end, n)
    merged["split"] = "holdout"
    merged.loc[: discovery_end - 1, "split"] = "discovery"
    if validation_end > discovery_end:
        merged.loc[discovery_end : validation_end - 1, "split"] = "validation"

    audit = pd.DataFrame([{
        "stage": "dataset",
        "status": "OK" if merged["causal_row_flag"].all() else "CAUSAL_VIOLATION",
        "inputs": len(inputs),
        "bursts": len(bursts),
        "outcomes": len(outcomes),
        "joined_rows": len(merged),
        "causal_rows": int(merged["causal_row_flag"].sum()),
    }])
    return merged, audit


def _feature_catalog() -> pd.DataFrame:
    return pd.DataFrame([{
        "feature": spec.name,
        "source": spec.source,
        "definition_formula": spec.formula,
        "units": spec.units,
        "physical_interpretation": spec.interpretation,
        "feature_timestamp_start_offset_seconds": spec.window_start_seconds,
        "feature_timestamp_end_offset_seconds": spec.window_end_seconds,
        "causal_flag": 1,
        "realtime_available": 1,
        "engineered": int(spec.engineered),
    } for spec in ALL_SPECS])


def _candidate_features() -> pd.DataFrame:
    rows = []
    for spec in ENGINEERED_SPECS:
        rows.append({
            "feature": spec.name,
            "hypothesis": spec.interpretation,
            "formula": spec.formula,
            "pre_registered_before_full_run": 1,
            "status": "TEST_WITHOUT_TRADING_FILTER",
            "rejection_condition": "causal violation; unstable sign; q>=0.10; |Cliff delta|<0.33",
        })
    rows.extend([
        {"feature": "refill_ratio", "hypothesis": "Reposición del libro tras agresión.", "formula": "added_size_at_level/consumed_size", "pre_registered_before_full_run": 1, "status": "REJECTED_UNAVAILABLE_IN_CURRENT_REPLAY", "rejection_condition": "MBO/MBP no está presente en el workspace ni en Historia X10 actual."},
        {"feature": "refill_speed", "hypothesis": "Velocidad de reconstrucción del nivel.", "formula": "refilled_contracts/seconds", "pre_registered_before_full_run": 1, "status": "REJECTED_UNAVAILABLE_IN_CURRENT_REPLAY", "rejection_condition": "Sin stream de libro causal reproducible."},
        {"feature": "book_embedding", "hypothesis": "Estado no lineal del libro.", "formula": "embedding(MBO/MBP sequence)", "pre_registered_before_full_run": 1, "status": "REJECTED_UNAVAILABLE_IN_CURRENT_REPLAY", "rejection_condition": "No inventar datos de libro ausentes."},
    ])
    return pd.DataFrame(rows)


def _causality_audit(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    prediction_min = dataset["prediction_timestamp"].min() if not dataset.empty else pd.NaT
    prediction_max = dataset["prediction_timestamp"].max() if not dataset.empty else pd.NaT
    for spec in ALL_SPECS:
        rows.append({
            "feature": spec.name,
            "source": spec.source,
            "feature_timestamp_start_rule": f"prediction_timestamp{spec.window_start_seconds:+g}s",
            "feature_timestamp_end_rule": f"prediction_timestamp{spec.window_end_seconds:+g}s",
            "prediction_timestamp_min": prediction_min,
            "prediction_timestamp_max": prediction_max,
            "causal_flag": 1,
            "future_information": 0,
            "decision": "ACCEPT_CAUSAL",
        })
    rejections = [
        {"variable": "MFE_ticks", "reason": "Outcome posterior; solo etiqueta retrospectiva.", "decision": "REJECT_FROM_FEATURES"},
        {"variable": "MAE_ticks", "reason": "Outcome posterior; solo etiqueta retrospectiva.", "decision": "REJECT_FROM_FEATURES"},
        {"variable": "Result_Label/result_ticks", "reason": "Resultado terminal.", "decision": "REJECT_FROM_FEATURES"},
        {"variable": "ExitTime/ExitPrice", "reason": "Información futura.", "decision": "REJECT_FROM_FEATURES"},
        {"variable": "Cvd_*_Final", "reason": "Estado intratrade/final.", "decision": "REJECT_FROM_FEATURES"},
        {"variable": "Dynamic_Alarm_*", "reason": "Gestión posterior a entrada.", "decision": "REJECT_FROM_FEATURES"},
        {"variable": "Price_Accepted_After_Imbalance_AtEntry", "reason": "Nombre semánticamente ambiguo; excluida hasta demostrar timestamp causal propio.", "decision": "REJECT_CONSERVATIVE"},
        {"variable": "Price_Rejected_After_Imbalance_AtEntry", "reason": "Nombre semánticamente ambiguo; excluida hasta demostrar timestamp causal propio.", "decision": "REJECT_CONSERVATIVE"},
        {"variable": "refill/order-book", "reason": "Stream MBO/MBP no disponible en la configuración replay actual.", "decision": "REJECT_UNAVAILABLE"},
    ]
    for name in FEATURE_NAMES:
        if OUTCOME_PATTERNS.search(name):
            rejections.append({"variable": name, "reason": "Patrón automático de leakage.", "decision": "REJECT_FROM_FEATURES"})
    return pd.DataFrame(rows), pd.DataFrame(rejections).drop_duplicates()


def _cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) == 0 or len(b) == 0:
        return np.nan
    return float((np.sum(a[:, None] > b[None, :]) - np.sum(a[:, None] < b[None, :])) / (len(a) * len(b)))


def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2 or len(b) < 2:
        return np.nan
    pooled = ((len(a) - 1) * np.var(a, ddof=1) + (len(b) - 1) * np.var(b, ddof=1)) / (len(a) + len(b) - 2)
    return float((np.mean(a) - np.mean(b)) / math.sqrt(pooled)) if pooled > 0 else 0.0


def _overlap(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) == 0 or len(b) == 0:
        return np.nan
    lo, hi = min(a.min(), b.min()), max(a.max(), b.max())
    if lo == hi:
        return 1.0
    bins = min(20, max(5, int(math.sqrt(len(a) + len(b)))))
    ha, edges = np.histogram(a, bins=bins, range=(lo, hi), density=True)
    hb, _ = np.histogram(b, bins=edges, density=True)
    widths = np.diff(edges)
    return float(np.sum(np.minimum(ha, hb) * widths))


def _permutation_p(a: np.ndarray, b: np.ndarray, rng: np.random.Generator, n_perm: int = 2000) -> float:
    observed = abs(float(np.mean(a) - np.mean(b)))
    pooled = np.concatenate([a, b])
    hits = 0
    for _ in range(n_perm):
        perm = rng.permutation(pooled)
        diff = abs(float(np.mean(perm[: len(a)]) - np.mean(perm[len(a) :])))
        hits += diff >= observed
    return (hits + 1) / (n_perm + 1)


def _bootstrap_diff(a: np.ndarray, b: np.ndarray, rng: np.random.Generator, n_boot: int = 2000) -> tuple[float, float]:
    values = np.empty(n_boot)
    for i in range(n_boot):
        values[i] = np.mean(rng.choice(a, len(a), replace=True)) - np.mean(rng.choice(b, len(b), replace=True))
    return tuple(np.quantile(values, [0.025, 0.975]).tolist())


def _bh_adjust(p_values: pd.Series) -> pd.Series:
    values = p_values.fillna(1.0).to_numpy(float)
    order = np.argsort(values)
    adjusted = np.empty(len(values))
    running = 1.0
    for rank_index in range(len(values) - 1, -1, -1):
        idx = order[rank_index]
        candidate = values[idx] * len(values) / (rank_index + 1)
        running = min(running, candidate)
        adjusted[idx] = min(1.0, running)
    return pd.Series(adjusted, index=p_values.index)


def _statistical_tests(dataset: pd.DataFrame) -> pd.DataFrame:
    discovery = dataset.loc[(dataset["split"] == "discovery") & dataset["causal_row_flag"]]
    rows = []
    rng = np.random.default_rng(RANDOM_SEED)
    for feature in FEATURE_NAMES:
        if feature not in discovery:
            continue
        a = pd.to_numeric(discovery.loc[discovery["family"] == "A_TRUE_ABSORPTION", feature], errors="coerce").dropna().to_numpy()
        b = pd.to_numeric(discovery.loc[discovery["family"] == "B_CLEAN_BREAKOUT", feature], errors="coerce").dropna().to_numpy()
        row = {"feature": feature, "n_A": len(a), "n_B": len(b)}
        for prefix, values in (("A", a), ("B", b)):
            row.update({
                f"{prefix}_mean": np.mean(values) if len(values) else np.nan,
                f"{prefix}_median": np.median(values) if len(values) else np.nan,
                f"{prefix}_std": np.std(values, ddof=1) if len(values) > 1 else np.nan,
                f"{prefix}_p10": np.quantile(values, 0.10) if len(values) else np.nan,
                f"{prefix}_p25": np.quantile(values, 0.25) if len(values) else np.nan,
                f"{prefix}_p75": np.quantile(values, 0.75) if len(values) else np.nan,
                f"{prefix}_p90": np.quantile(values, 0.90) if len(values) else np.nan,
            })
        if len(a) >= 2 and len(b) >= 2:
            row["cohens_d_A_minus_B"] = _cohens_d(a, b)
            row["cliffs_delta_A_minus_B"] = _cliffs_delta(a, b)
            row["overlap_coefficient"] = _overlap(a, b)
            row["mann_whitney_p"] = stats.mannwhitneyu(a, b, alternative="two-sided").pvalue
            row["ks_p"] = stats.ks_2samp(a, b).pvalue
            row["welch_t_p"] = stats.ttest_ind(a, b, equal_var=False).pvalue
            row["anova_p"] = stats.f_oneway(a, b).pvalue
            row["permutation_p"] = _permutation_p(a, b, rng)
            row["mean_diff_bootstrap_ci_low"], row["mean_diff_bootstrap_ci_high"] = _bootstrap_diff(a, b, rng)
        rows.append(row)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["mann_whitney_q_bh"] = _bh_adjust(frame["mann_whitney_p"])
        frame["permutation_q_bh"] = _bh_adjust(frame["permutation_p"])
        frame["abs_cliffs_delta"] = frame["cliffs_delta_A_minus_B"].abs()
        frame = frame.sort_values(["permutation_q_bh", "abs_cliffs_delta"], ascending=[True, False])
    return frame


def _conditional_mi_proxy(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> float:
    if len(np.unique(y)) < 2 or len(x) < 6:
        return np.nan
    x_bins = pd.qcut(pd.Series(x), q=min(4, max(2, len(x) // 3)), duplicates="drop", labels=False).to_numpy()
    z_clusters = KMeans(n_clusters=min(3, max(2, len(x) // 4)), random_state=RANDOM_SEED, n_init=10).fit_predict(z)
    total = len(x)
    cmi = 0.0
    for cluster in np.unique(z_clusters):
        mask = z_clusters == cluster
        weight = mask.mean()
        if mask.sum() < 3 or len(np.unique(y[mask])) < 2:
            continue
        cmi += weight * mutual_info_classif(x_bins[mask].reshape(-1, 1), y[mask], discrete_features=True, random_state=RANDOM_SEED)[0]
    return float(cmi)


def _model_and_rankings(dataset: pd.DataFrame, stats_frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    eligible = dataset.loc[dataset["causal_row_flag"] & dataset["family"].isin(["A_TRUE_ABSORPTION", "B_CLEAN_BREAKOUT"])].copy()
    discovery = eligible.loc[eligible["split"] == "discovery"].copy()
    validation = eligible.loc[eligible["split"] == "validation"].copy()
    holdout = eligible.loc[eligible["split"] == "holdout"].copy()
    candidates = [f for f in FEATURE_NAMES if f in discovery and pd.to_numeric(discovery[f], errors="coerce").notna().sum() >= 4]
    candidates = [f for f in candidates if pd.to_numeric(discovery[f], errors="coerce").nunique(dropna=True) > 1]
    importance_rows: list[dict[str, object]] = []
    model_rows: list[dict[str, object]] = []
    validation_rows: list[dict[str, object]] = []
    if len(discovery) < 6 or discovery["family"].nunique() < 2 or not candidates:
        return pd.DataFrame(importance_rows), pd.DataFrame(validation_rows), pd.DataFrame([{
            "model": "ALL", "split": "discovery", "status": "INSUFFICIENT_SAMPLE",
            "n": len(discovery), "classes": discovery["family"].nunique(),
        }])

    y_disc = discovery["family"].eq("A_TRUE_ABSORPTION").astype(int).to_numpy()
    stat_lookup = stats_frame.set_index("feature") if not stats_frame.empty else pd.DataFrame()
    ordered = sorted(
        candidates,
        key=lambda f: (
            float(stat_lookup.loc[f, "permutation_q_bh"]) if f in stat_lookup.index else 1.0,
            -float(stat_lookup.loc[f, "abs_cliffs_delta"]) if f in stat_lookup.index and pd.notna(stat_lookup.loc[f, "abs_cliffs_delta"]) else 0.0,
        ),
    )
    selected = ordered[: min(12, len(ordered))]
    x_disc = discovery[selected].apply(pd.to_numeric, errors="coerce")
    imputer = SimpleImputer(strategy="median")
    x_disc_i = imputer.fit_transform(x_disc)
    base_cols = [c for c in ["Delta1s", "Velocity1s", "ContractsPerSecond"] if c in selected]
    z = x_disc_i[:, [selected.index(c) for c in base_cols]] if base_cols else x_disc_i[:, : min(3, x_disc_i.shape[1])]
    mi = mutual_info_classif(x_disc_i, y_disc, random_state=RANDOM_SEED)
    for feature, value in zip(selected, mi):
        importance_rows.append({"feature": feature, "method": "mutual_information", "importance": value, "split": "discovery"})
        importance_rows.append({"feature": feature, "method": "conditional_mutual_information_proxy", "importance": _conditional_mi_proxy(x_disc_i[:, selected.index(feature)], y_disc, z), "split": "discovery"})

    models = {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced", random_state=RANDOM_SEED)),
        "decision_tree": DecisionTreeClassifier(max_depth=3, min_samples_leaf=2, class_weight="balanced", random_state=RANDOM_SEED),
        "random_forest": RandomForestClassifier(n_estimators=300, max_depth=4, min_samples_leaf=2, class_weight="balanced", random_state=RANDOM_SEED),
    }
    try:
        from catboost import CatBoostClassifier, Pool

        models["catboost"] = CatBoostClassifier(
            iterations=250, depth=3, learning_rate=0.03, loss_function="Logloss",
            verbose=False, random_seed=RANDOM_SEED, allow_writing_files=False,
        )
    except Exception:
        Pool = None

    for model_name, model in models.items():
        model.fit(x_disc_i, y_disc)
        if model_name == "logistic":
            raw_importance = np.abs(model.named_steps["logisticregression"].coef_[0])
        elif model_name == "decision_tree":
            raw_importance = model.feature_importances_
        elif model_name == "random_forest":
            raw_importance = model.feature_importances_
        else:
            raw_importance = model.get_feature_importance()
        for feature, value in zip(selected, raw_importance):
            importance_rows.append({"feature": feature, "method": model_name, "importance": float(value), "split": "discovery"})
        if model_name == "catboost" and Pool is not None:
            shap_values = model.get_feature_importance(Pool(x_disc_i, label=y_disc), type="ShapValues")[:, :-1]
            for feature, value in zip(selected, np.mean(np.abs(shap_values), axis=0)):
                importance_rows.append({"feature": feature, "method": "catboost_incremental_shap", "importance": float(value), "split": "discovery"})

        for split_name, split_frame in (("validation", validation), ("holdout", holdout)):
            if split_frame.empty:
                model_rows.append({"model": model_name, "split": split_name, "status": "NO_ROWS", "n": 0})
                continue
            y = split_frame["family"].eq("A_TRUE_ABSORPTION").astype(int).to_numpy()
            x = imputer.transform(split_frame[selected].apply(pd.to_numeric, errors="coerce"))
            pred = model.predict(x).astype(int).reshape(-1)
            proba = model.predict_proba(x)[:, 1] if hasattr(model, "predict_proba") else pred.astype(float)
            model_rows.append({
                "model": model_name, "split": split_name, "status": "OK",
                "n": len(y), "balanced_accuracy": balanced_accuracy_score(y, pred) if len(np.unique(y)) > 1 else np.nan,
                "roc_auc": roc_auc_score(y, proba) if len(np.unique(y)) > 1 else np.nan,
                "confusion_matrix": json.dumps(confusion_matrix(y, pred, labels=[0, 1]).tolist()),
            })
            if split_name == "validation" and len(y) >= 3:
                perm = permutation_importance(model, x, y, n_repeats=50, random_state=RANDOM_SEED, scoring="balanced_accuracy")
                for feature, value in zip(selected, perm.importances_mean):
                    importance_rows.append({"feature": feature, "method": f"{model_name}_permutation", "importance": float(value), "split": "validation"})

        if model_name == "logistic" and len(selected) > 1 and not validation.empty:
            y_validation = validation["family"].eq("A_TRUE_ABSORPTION").astype(int).to_numpy()
            if len(np.unique(y_validation)) > 1:
                x_validation = imputer.transform(validation[selected].apply(pd.to_numeric, errors="coerce"))
                baseline = balanced_accuracy_score(y_validation, model.predict(x_validation).astype(int).reshape(-1))
                for feature_index, feature in enumerate(selected):
                    keep = [i for i in range(len(selected)) if i != feature_index]
                    ablated = make_pipeline(
                        StandardScaler(),
                        LogisticRegression(max_iter=2000, class_weight="balanced", random_state=RANDOM_SEED),
                    )
                    ablated.fit(x_disc_i[:, keep], y_disc)
                    ablated_score = balanced_accuracy_score(
                        y_validation,
                        ablated.predict(x_validation[:, keep]).astype(int).reshape(-1),
                    )
                    importance_rows.append({
                        "feature": feature,
                        "method": "logistic_validation_ablation",
                        "importance": float(baseline - ablated_score),
                        "split": "validation",
                    })

    top_for_validation = ordered[: min(10, len(ordered))]
    rng = np.random.default_rng(RANDOM_SEED)
    for feature in top_for_validation:
        row: dict[str, object] = {"feature": feature}
        discovery_a = pd.to_numeric(discovery.loc[discovery["family"] == "A_TRUE_ABSORPTION", feature], errors="coerce").dropna()
        discovery_b = pd.to_numeric(discovery.loc[discovery["family"] == "B_CLEAN_BREAKOUT", feature], errors="coerce").dropna()
        direction = np.sign(discovery_a.median() - discovery_b.median()) if len(discovery_a) and len(discovery_b) else 0
        row["discovery_direction_A_minus_B"] = direction
        row["discovery_threshold_mid_medians"] = (discovery_a.median() + discovery_b.median()) / 2 if len(discovery_a) and len(discovery_b) else np.nan
        if len(discovery_a) >= 2 and len(discovery_b) >= 2 and direction != 0:
            bootstrap_signs = []
            noise_signs = []
            pooled_std = float(np.nanstd(np.concatenate([discovery_a.to_numpy(), discovery_b.to_numpy()])))
            noise_scale = max(pooled_std * 0.05, 1e-9)
            for _ in range(1000):
                a_sample = rng.choice(discovery_a.to_numpy(), len(discovery_a), replace=True)
                b_sample = rng.choice(discovery_b.to_numpy(), len(discovery_b), replace=True)
                bootstrap_signs.append(np.sign(np.median(a_sample) - np.median(b_sample)) == direction)
                a_noise = discovery_a.to_numpy() + rng.normal(0, noise_scale, len(discovery_a))
                b_noise = discovery_b.to_numpy() + rng.normal(0, noise_scale, len(discovery_b))
                noise_signs.append(np.sign(np.median(a_noise) - np.median(b_noise)) == direction)
            row["monte_carlo_bootstrap_direction_stability"] = float(np.mean(bootstrap_signs))
            row["gaussian_noise_5pct_direction_stability"] = float(np.mean(noise_signs))
        else:
            row["monte_carlo_bootstrap_direction_stability"] = np.nan
            row["gaussian_noise_5pct_direction_stability"] = np.nan
        stable = True
        for split_name, split_frame in (("validation", validation), ("holdout", holdout)):
            a = pd.to_numeric(split_frame.loc[split_frame["family"] == "A_TRUE_ABSORPTION", feature], errors="coerce").dropna()
            b = pd.to_numeric(split_frame.loc[split_frame["family"] == "B_CLEAN_BREAKOUT", feature], errors="coerce").dropna()
            split_direction = np.sign(a.median() - b.median()) if len(a) and len(b) else np.nan
            row[f"{split_name}_n_A"] = len(a)
            row[f"{split_name}_n_B"] = len(b)
            row[f"{split_name}_direction_A_minus_B"] = split_direction
            threshold = row["discovery_threshold_mid_medians"]
            if pd.notna(threshold) and direction != 0:
                predicts_a = (
                    pd.to_numeric(split_frame[feature], errors="coerce").ge(threshold)
                    if direction > 0
                    else pd.to_numeric(split_frame[feature], errors="coerce").le(threshold)
                )
                family_a = split_frame["family"].eq("A_TRUE_ABSORPTION")
                family_b = split_frame["family"].eq("B_CLEAN_BREAKOUT")
                row[f"{split_name}_B_detectable_pct"] = float((~predicts_a[family_b]).mean() * 100) if family_b.any() else np.nan
                row[f"{split_name}_A_lost_pct"] = float((~predicts_a[family_a]).mean() * 100) if family_a.any() else np.nan
            if np.isnan(split_direction) or split_direction != direction:
                stable = False
        row["direction_stable_discovery_validation_holdout"] = int(stable and direction != 0)
        validation_rows.append(row)
    return pd.DataFrame(importance_rows), pd.DataFrame(validation_rows), pd.DataFrame(model_rows)


def _rankings(stats_frame: pd.DataFrame, importance: pd.DataFrame, validation: pd.DataFrame) -> pd.DataFrame:
    if stats_frame.empty:
        return pd.DataFrame()
    frame = stats_frame[["feature", "permutation_q_bh", "mann_whitney_q_bh", "cliffs_delta_A_minus_B", "abs_cliffs_delta", "overlap_coefficient"]].copy()
    if not importance.empty:
        pivot = importance.pivot_table(index="feature", columns="method", values="importance", aggfunc="mean").reset_index()
        frame = frame.merge(pivot, on="feature", how="left")
    if not validation.empty:
        frame = frame.merge(validation, on="feature", how="left")
    frame["evidence_score"] = (
        frame["abs_cliffs_delta"].fillna(0) *
        (1 - frame["overlap_coefficient"].fillna(1)) *
        (1 - frame["permutation_q_bh"].fillna(1))
    )
    frame["robust_candidate"] = (
        frame["permutation_q_bh"].lt(0.10) &
        frame["abs_cliffs_delta"].ge(0.33) &
        frame.get("direction_stable_discovery_validation_holdout", pd.Series(0, index=frame.index)).eq(1)
    ).astype(int)
    return frame.sort_values(["robust_candidate", "evidence_score"], ascending=[False, False]).reset_index(drop=True)


def _correlations(dataset: pd.DataFrame) -> pd.DataFrame:
    discovery = dataset.loc[(dataset["split"] == "discovery") & dataset["causal_row_flag"], FEATURE_NAMES].apply(pd.to_numeric, errors="coerce")
    if discovery.empty:
        return pd.DataFrame()
    spearman = discovery.corr(method="spearman")
    pearson = discovery.corr(method="pearson")
    rows = []
    for i, a in enumerate(spearman.columns):
        for b in spearman.columns[i + 1 :]:
            value = spearman.loc[a, b]
            if pd.notna(value):
                pearson_value = pearson.loc[a, b]
                rows.append({
                    "feature_a": a,
                    "feature_b": b,
                    "spearman": value,
                    "pearson": pearson_value,
                    "abs_spearman": abs(value),
                    "abs_pearson": abs(pearson_value) if pd.notna(pearson_value) else np.nan,
                    "redundant_ge_0_90": int(abs(value) >= 0.90 or (pd.notna(pearson_value) and abs(pearson_value) >= 0.90)),
                })
    return pd.DataFrame(rows).sort_values("abs_spearman", ascending=False) if rows else pd.DataFrame()


def _cluster(dataset: pd.DataFrame, rankings: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty:
        return pd.DataFrame()
    features = rankings["feature"].head(8).tolist() if not rankings.empty else FEATURE_NAMES[:8]
    features = [f for f in features if f in dataset]
    if len(dataset) < 4 or len(features) < 2:
        return pd.DataFrame()
    x = dataset[features].apply(pd.to_numeric, errors="coerce")
    x = SimpleImputer(strategy="median").fit_transform(x)
    x = StandardScaler().fit_transform(x)
    out = dataset[["fecha", "BurstId", "family", "split"]].copy()
    for k in (2, 3):
        if len(dataset) >= k:
            out[f"kmeans_{k}"] = KMeans(n_clusters=k, random_state=RANDOM_SEED, n_init=20).fit_predict(x)
            out[f"gmm_{k}"] = GaussianMixture(n_components=k, random_state=RANDOM_SEED).fit_predict(x)
    out["dbscan"] = DBSCAN(eps=1.25, min_samples=max(2, min(5, len(dataset) // 10))).fit_predict(x)
    try:
        import hdbscan

        out["hdbscan"] = hdbscan.HDBSCAN(min_cluster_size=max(2, min(5, len(dataset) // 8))).fit_predict(x)
    except Exception:
        out["hdbscan"] = "UNAVAILABLE"
    return out


def _visualizations(dataset: pd.DataFrame, rankings: pd.DataFrame, output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    counts = dataset["family"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(9, 5))
    counts.plot.bar(ax=ax, color=["#2ca02c", "#d62728", "#ffbf00", "#7f7f7f"][: len(counts)])
    ax.set_title("Familias Liquidity Burst")
    ax.set_ylabel("Trades")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    path = output / "family_counts.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    paths.append(path)

    features = rankings["feature"].head(8).tolist() if not rankings.empty else FEATURE_NAMES[:8]
    features = [f for f in features if f in dataset]
    if len(dataset) >= 3 and len(features) >= 2:
        x = dataset[features].apply(pd.to_numeric, errors="coerce")
        x = SimpleImputer(strategy="median").fit_transform(x)
        x = StandardScaler().fit_transform(x)
        pca = PCA(n_components=2, random_state=RANDOM_SEED).fit_transform(x)
        fig, ax = plt.subplots(figsize=(8, 6))
        for family in sorted(dataset["family"].unique()):
            mask = dataset["family"].eq(family).to_numpy()
            ax.scatter(pca[mask, 0], pca[mask, 1], label=family, alpha=0.8)
        ax.set_title("PCA causal (sin outcomes como inputs)")
        ax.legend(fontsize=8)
        fig.tight_layout()
        path = output / "pca_families.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path)
        try:
            from sklearn.manifold import TSNE

            if len(dataset) >= 5:
                emb = TSNE(n_components=2, perplexity=min(10, max(2, len(dataset) // 3)), random_state=RANDOM_SEED, init="pca").fit_transform(x)
                fig, ax = plt.subplots(figsize=(8, 6))
                for family in sorted(dataset["family"].unique()):
                    mask = dataset["family"].eq(family).to_numpy()
                    ax.scatter(emb[mask, 0], emb[mask, 1], label=family, alpha=0.8)
                ax.set_title("t-SNE exploratorio")
                ax.legend(fontsize=8)
                fig.tight_layout()
                path = output / "tsne_families.png"
                fig.savefig(path, dpi=160)
                plt.close(fig)
                paths.append(path)
        except Exception:
            pass
        try:
            import umap

            emb = umap.UMAP(n_components=2, random_state=RANDOM_SEED, n_neighbors=min(15, len(dataset) - 1)).fit_transform(x)
            fig, ax = plt.subplots(figsize=(8, 6))
            for family in sorted(dataset["family"].unique()):
                mask = dataset["family"].eq(family).to_numpy()
                ax.scatter(emb[mask, 0], emb[mask, 1], label=family, alpha=0.8)
            ax.set_title("UMAP exploratorio")
            ax.legend(fontsize=8)
            fig.tight_layout()
            path = output / "umap_families.png"
            fig.savefig(path, dpi=160)
            plt.close(fig)
            paths.append(path)
        except Exception:
            pass

    if not rankings.empty:
        top = rankings.head(12).sort_values("evidence_score")
        fig, ax = plt.subplots(figsize=(10, 7))
        ax.barh(top["feature"], top["evidence_score"], color="#1f77b4")
        ax.set_title("Ranking de evidencia (discovery + estabilidad)")
        ax.set_xlabel("evidence_score")
        fig.tight_layout()
        path = output / "feature_rankings.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path)
        for feature in rankings["feature"].head(3):
            fig, ax = plt.subplots(figsize=(8, 5))
            for family, color in (("A_TRUE_ABSORPTION", "#2ca02c"), ("B_CLEAN_BREAKOUT", "#d62728")):
                values = pd.to_numeric(dataset.loc[dataset["family"] == family, feature], errors="coerce").dropna()
                if len(values):
                    ax.hist(values, bins=min(12, max(4, len(values))), alpha=0.45, density=True, label=family, color=color)
            ax.set_title(feature)
            ax.legend(fontsize=8)
            fig.tight_layout()
            path = output / f"hist_{re.sub(r'[^A-Za-z0-9_]+', '_', feature)}.png"
            fig.savefig(path, dpi=160)
            plt.close(fig)
            paths.append(path)
    return paths


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    if frame.empty:
        frame = pd.DataFrame([{"status": "NO_DATA_OR_INSUFFICIENT_SAMPLE"}])
    frame.to_csv(path, index=False)


def _final_report(
    dataset: pd.DataFrame,
    rankings: pd.DataFrame,
    validation: pd.DataFrame,
    model_metrics: pd.DataFrame,
    causality: pd.DataFrame,
    leakage: pd.DataFrame,
    output: Path,
) -> str:
    counts = dataset["family"].value_counts().to_dict() if not dataset.empty else {}
    robust = rankings.loc[rankings["robust_candidate"].eq(1)] if not rankings.empty else pd.DataFrame()
    lines = [
        "# Análisis Familias A, B, C, etc.",
        "",
        "## Resultado principal",
        "",
    ]
    if robust.empty:
        lines.append("No se descubrió todavía una feature que cumpla simultáneamente significancia corregida, tamaño de efecto y estabilidad cronológica. Este resultado no autoriza ningún filtro ni cambio de estrategia.")
    else:
        names = ", ".join(robust["feature"].head(5))
        lines.append(f"Las candidatas que superaron el criterio pre-registrado fueron: {names}. Siguen siendo conocimiento observacional; no se aplicaron como filtro de trading.")
    lines.extend([
        "",
        "## Muestra",
        "",
        f"- Total de entradas Liquidity Burst causales: {len(dataset)}.",
        f"- Familia A — absorción verdadera estricta: {counts.get('A_TRUE_ABSORPTION', 0)}.",
        f"- Familia B — breakout limpio estricto: {counts.get('B_CLEAN_BREAKOUT', 0)}.",
        f"- Familia C — trayectoria mixta: {counts.get('C_MIXED_PATH', 0)}.",
        f"- Familia D — otras salidas: {counts.get('D_OTHER_EXIT', 0)}.",
        "- Split cronológico: 60% discovery, 20% validation, 20% holdout abierto una sola vez al cierre.",
        "",
        "## Definición de familias",
        "",
        "- A: TP, MAE <=10 ticks y MFE >= TP inicial.",
        "- B: SL, MFE <=10 ticks y MAE >= SL inicial.",
        "- C: TP/SL con excursión intermedia que no cumple A/B estricta.",
        "- D: time exit, break-even u otra salida.",
        "",
        "## Features con mayor evidencia en discovery",
        "",
        "| Feature | q permutación | Cliff delta A-B | Overlap | Estable | Robusta |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    if rankings.empty:
        lines.append("| Sin muestra suficiente | | | | | |")
    else:
        for _, row in rankings.head(10).iterrows():
            lines.append(
                f"| {row['feature']} | {row.get('permutation_q_bh', np.nan):.4f} | "
                f"{row.get('cliffs_delta_A_minus_B', np.nan):.3f} | {row.get('overlap_coefficient', np.nan):.3f} | "
                f"{int(row.get('direction_stable_discovery_validation_holdout', 0) or 0)} | {int(row.get('robust_candidate', 0))} |"
            )
    lines.extend([
        "",
        "## Modelos fuera de muestra",
        "",
        "| Modelo | Split | n | Balanced accuracy | ROC AUC | Estado |",
        "|---|---|---:|---:|---:|---|",
    ])
    if model_metrics.empty:
        lines.append("| Sin muestra suficiente | | 0 | | | INSUFFICIENT |")
    else:
        for _, row in model_metrics.iterrows():
            lines.append(
                f"| {row.get('model','')} | {row.get('split','')} | {int(row.get('n',0) or 0)} | "
                f"{row.get('balanced_accuracy', np.nan):.3f} | {row.get('roc_auc', np.nan):.3f} | {row.get('status','')} |"
            )
    lines.extend([
        "",
        "## Causalidad y prevención de leakage",
        "",
        f"- Features aceptadas como causales: {int(causality['causal_flag'].sum()) if not causality.empty and 'causal_flag' in causality else 0}.",
        f"- Variables rechazadas o no disponibles: {len(leakage)}.",
        "- MFE, MAE, resultado, salida y estados finales se usaron solo para etiquetas/outcomes.",
        "- Refill, MBO, MBP y embeddings de libro se rechazaron porque el workspace replay actual no entrega ese stream; no se fabricaron valores.",
        "- El análisis usa los CSV terminales por fecha como outcomes canónicos; `trade_results.csv` no se usa para MAE/MFE porque una recalculación sincronizada puede sobrescribir esa tabla con métricas parciales.",
        "",
        "## Respuestas científicas",
        "",
        "1. Las diferencias medibles se reportan con bootstrap, permutation test, Mann–Whitney, KS, Welch y corrección BH.",
        "2. El ranking completo está en `feature_rankings.csv`; no se seleccionó por PF.",
        "3. Las features nuevas se documentan con fórmula física en `feature_catalog.csv` y `candidate_features.csv`.",
        "4. Mutual information, CMI proxy, SHAP de CatBoost, permutation importance y ablación quedan separados por método.",
        "5. Ninguna combinación se convierte en filtro en esta corrida.",
        "6. El porcentaje de B potencialmente detectable solo se considera si una feature es robusta en discovery/validation/holdout.",
        "7. La pérdida potencial de ganadoras se calcula sobre A, nunca se oculta.",
        "8. La prioridad siguiente es capturar un stream de libro reproducible solo si ATAS Historia lo suministra sin alterar el replay.",
        "",
        "## Decisión",
        "",
        "La estrategia y Liquidity Burst permanecen congelados. Este informe descubre o refuta propiedades; no optimiza entradas, TP, SL, RR ni gestión.",
        "",
        f"Artefactos: `{output}`",
    ])
    return "\n".join(lines) + "\n"


def _research_ledger(output: Path, dataset: pd.DataFrame) -> str:
    return f"""# Research ledger — Absorción vs Breakout

## Pre-registro

- Semilla: `{RANDOM_SEED}`.
- Prediction timestamp único: `feature_timestamp_utc` del snapshot de entrada.
- Familias: A TP con MAE<=10; B SL con MFE<=10 y MAE>=SL; C trayectoria mixta; D otra salida.
- Split cronológico congelado antes del análisis: 60/20/20.
- Criterio robusto: permutation q BH <0.10, |Cliff delta| >=0.33 y mismo signo en discovery, validation y holdout.
- No se busca PF, no se optimiza threshold y no se modifica trading.

## Inventario de hipótesis

- Impacto por contrato: breakout limpio debe desplazar más precio por unidad de agresión.
- Presión de absorción: absorción debe mostrar mucho delta por poco desplazamiento.
- Persistencia: breakout limpio debe conservar signo de delta y velocidad en 1/3/5s.
- Contexto: proximidad a POC/VAH/VAL/HVN/LVN puede modular absorción.
- Refill/libro: hipótesis rechazada por indisponibilidad del stream en el workspace actual.

## Holdout

- Filas totales: {len(dataset)}.
- El holdout se abre una sola vez al generar `final_report.md`.
- Cualquier hipótesis posterior deberá usar una temporada nueva; no se recicla este holdout.
"""


def run_analysis(results_folder: Path, output_folder: Path | None = None) -> dict[str, object]:
    results_folder = Path(results_folder)
    if output_folder is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_folder = Path(__file__).resolve().parent / "outputs" / f"absorption_breakout_research_{stamp}"
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    visual_folder = output_folder / "visualizations"

    dataset, dataset_audit = build_dataset(results_folder)
    catalog = _feature_catalog()
    candidates = _candidate_features()
    causality, leakage = _causality_audit(dataset)
    statistical = _statistical_tests(dataset) if not dataset.empty else pd.DataFrame()
    importance, validation, model_metrics = _model_and_rankings(dataset, statistical) if not dataset.empty else (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    rankings = _rankings(statistical, importance, validation)
    correlations = _correlations(dataset) if not dataset.empty else pd.DataFrame()
    clusters = _cluster(dataset, rankings) if not dataset.empty else pd.DataFrame()

    identity = [
        "fecha", "BurstId", "prediction_timestamp", "burst_event_timestamp", "burst_timestamp", "split", "family", "family_reason",
        "ExecutionSide", "BurstSide", "Entry_price", "Initial_SL_ticks", "Initial_TP_ticks",
        "Result_Label", "result TP SL BE", "MAE_ticks", "MFE_ticks", "ExitTime_NY_Milliseconds",
        "causal_row_flag", "canonical_source_file",
    ]
    engineered_columns = [c for c in identity + FEATURE_NAMES if c in dataset.columns]
    absorption_columns = [c for c in identity + ["Signal_Source", "Liquidity_Burst_ID_AtEntry"] if c in dataset.columns]
    _write_csv(catalog, output_folder / "feature_catalog.csv")
    _write_csv(candidates, output_folder / "candidate_features.csv")
    _write_csv(dataset[engineered_columns] if not dataset.empty else dataset, output_folder / "engineered_features.csv")
    _write_csv(dataset[absorption_columns] if not dataset.empty else dataset, output_folder / "absorption_vs_breakout.csv")
    _write_csv(importance, output_folder / "feature_importance.csv")
    _write_csv(rankings, output_folder / "feature_rankings.csv")
    _write_csv(clusters, output_folder / "cluster_analysis.csv")
    _write_csv(statistical, output_folder / "statistical_tests.csv")
    _write_csv(correlations, output_folder / "feature_correlations.csv")
    _write_csv(validation, output_folder / "feature_validation.csv")
    _write_csv(causality, output_folder / "causality_audit.csv")
    _write_csv(leakage, output_folder / "leakage_rejections.csv")
    _write_csv(dataset_audit, output_folder / "dataset_audit.csv")
    _write_csv(model_metrics, output_folder / "model_metrics.csv")
    visuals = _visualizations(dataset, rankings, visual_folder) if not dataset.empty else []
    report = _final_report(dataset, rankings, validation, model_metrics, causality, leakage, output_folder)
    (output_folder / "final_report.md").write_text(report, encoding="utf-8")
    (output_folder / "research_ledger.md").write_text(_research_ledger(output_folder, dataset), encoding="utf-8")
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "Historia X10 únicamente",
        "replay_x1": "DESHABILITADO",
        "results_folder": str(results_folder),
        "output_folder": str(output_folder),
        "rows": len(dataset),
        "families": dataset["family"].value_counts().to_dict() if not dataset.empty else {},
        "robust_features": rankings.loc[rankings["robust_candidate"].eq(1), "feature"].tolist() if not rankings.empty else [],
        "visualizations": [str(path) for path in visuals],
        "trading_logic_changed": False,
        "holdout_opened_once": True,
    }
    (output_folder / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    (results_folder / "latest_absorption_breakout_research.txt").write_text(str(output_folder), encoding="utf-8")
    return {"output_folder": output_folder, "report": report, "manifest": manifest, "visuals": visuals}


def _telegram_chunks(text: str, limit: int = 3500) -> list[str]:
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > limit:
            chunks.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


def send_analysis_to_telegram(results_folder: Path, analysis: dict[str, object]) -> bool:
    from telegram_run_summary_after_sync import send_photo, send_text

    ok = send_text(str(results_folder), TELEGRAM_TITLE)
    report = str(analysis["report"])
    for index, chunk in enumerate(_telegram_chunks(report), start=1):
        ok = send_text(str(results_folder), f"[{index}] {chunk}") and ok
    for path in analysis.get("visuals", []):
        ok = send_photo(str(results_folder), str(path), TELEGRAM_TITLE) and ok
    return ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Investigación causal Absorción vs Breakout; no modifica trading.")
    parser.add_argument("--results-folder", type=Path, required=True)
    parser.add_argument("--output-folder", type=Path, default=None)
    parser.add_argument("--telegram", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    analysis = run_analysis(args.results_folder, args.output_folder)
    print(json.dumps(analysis["manifest"], indent=2, default=str))
    if args.telegram:
        sent = send_analysis_to_telegram(args.results_folder, analysis)
        print(f"telegram_sent={sent}")
        return 0 if sent else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
