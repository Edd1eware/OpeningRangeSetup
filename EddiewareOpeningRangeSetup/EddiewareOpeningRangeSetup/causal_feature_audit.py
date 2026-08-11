from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence


FORBIDDEN_FEATURE_PATTERNS: tuple[str, ...] = (
    r"(^|_)final($|_)",
    r"(^|_)resolved($|_)",
    r"(^|_)winner($|_)",
    r"(^|_)loser($|_)",
    r"(^|_)outcome($|_)",
    r"(^|_)future($|_)",
    r"(^|_)exit($|_)",
    r"(^|_)profit($|_)",
    r"(^|_)mfe($|_)",
    r"(^|_)mae($|_)",
    r"(^|_)result($|_)",
    r"(^|_)targetreached($|_)",
    r"(^|_)stopreached($|_)",
    r"(^|_)closed($|_)",
    r"(^|_)finished($|_)",
    r"(^|_)dynamic($|_)",
    r"(^|_)alarm($|_)",
    r"(^|_)current($|_)",
    r"(^|_)state($|_)",
    r"(^|_)update(d)?($|_)",
    r"(^|_)recalculate($|_)",
    r"(^|_)refresh($|_)",
    r"(^|_)rewrite($|_)",
    r"(^|_)during($|_)",
    r"(^|_)trail($|_)",
    r"(^|_)breakeven($|_)",
    r"(^|_)tp($|_)",
    r"(^|_)sl($|_)",
    r"cvd_pullback_label",
    r"result\s*tp\s*sl\s*be",
    r"tp_and_sl",
)

ENTRY_SUFFIX = "_AtEntry"

ALLOWED_FEATURE_COLUMNS: frozenset[str] = frozenset(
    {
        "Side_AtEntry",
        "Signal_Source_AtEntry",
        "Speed_Profile_AtEntry",
        "Score_AtEntry",
        "OR_Range_AtEntry",
        "OR_Low_AtEntry",
        "OR_High_AtEntry",
        "VWAP_AtEntry",
        "Body_AtEntry",
        "Volume_AtEntry",
        "Delta_AtEntry",
        "Cumulative_Delta_AtEntry",
        "Cvd_Label_AtEntry",
        "Previous_Volume_AtEntry",
        "Previous_Delta_AtEntry",
        "Volume_Increasing_AtEntry",
        "Delta_Change_AtEntry",
        "Delta_With_Side_AtEntry",
        "Price_Accepted_After_Imbalance_AtEntry",
        "Price_Rejected_After_Imbalance_AtEntry",
        "BreakOut_SPEED_AtEntry",
        "BreakOut_TICKS_PER_SEC_AtEntry",
        "Speed_Elapsed_SECONDS_AtEntry",
        "Speed_Replay_Fallback_AtEntry",
        "Speed_Timing_Source_AtEntry",
        "Range_OK_AtEntry",
        "Body_OK_AtEntry",
        "Volume_OK_AtEntry",
        "Delta_OK_AtEntry",
        "Time_OK_AtEntry",
        "VWAP_OK_AtEntry",
        "Speed_OK_AtEntry",
        "Raw_Speed_Label_AtEntry",
        "APlus_Structure_AtEntry",
        "APlus_Absorption_AtEntry",
        "APlus_Speed_AtEntry",
        "APlus_Speed_Setup_Confirmed_AtEntry",
        "Buy_Imbalance_Count_AtEntry",
        "Sell_Imbalance_Count_AtEntry",
        "Execution_Side_Imbalance_Count_AtEntry",
        "Imbalance_Group_3_AtEntry",
        "Imbalance_Group_Price_AtEntry",
        "Imbalance_Count_AtEntry",
        "Speed_Ignored_By_Structure_AtEntry",
        "OR_Regime_AtEntry",
        "Vol_Regime_AtEntry",
    }
)

KEY_OR_META_COLUMNS: frozenset[str] = frozenset(
    {
        "trade_id",
        "Input_VERSION",
        "Result_VERSION",
        "fecha",
        "decision_timestamp",
        "feature_timestamp",
        "entry_timestamp",
        "feature_timestamp_utc",
        "entry_timestamp_utc",
        "outcome_timestamp",
        "EntryBar",
        "Entry_price",
    }
)


@dataclass(frozen=True)
class FeatureAuditViolation:
    column: str
    reason: str


def normalize_column(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def forbidden_reason(column: str) -> str | None:
    norm = normalize_column(column)
    for pattern in FORBIDDEN_FEATURE_PATTERNS:
        if re.search(pattern, norm):
            return f"contains forbidden future/outcome token `{pattern}`"
    return None


def audit_feature_columns(feature_columns: Sequence[str]) -> None:
    """Abort if any selected optimizer feature can contain future information."""
    violations: list[FeatureAuditViolation] = []
    for column in feature_columns:
        if column in KEY_OR_META_COLUMNS:
            violations.append(FeatureAuditViolation(column, "metadata/key column is not a model feature"))
            continue
        if column not in ALLOWED_FEATURE_COLUMNS:
            violations.append(FeatureAuditViolation(column, "not in causal feature allowlist"))
            continue
        reason = forbidden_reason(column)
        if reason:
            violations.append(FeatureAuditViolation(column, reason))

    if violations:
        details = "\n".join(f"- {v.column}: {v.reason}" for v in violations)
        raise RuntimeError(f"Look-ahead/leakage feature audit failed:\n{details}")


def classify_column(column: str) -> tuple[str, str]:
    """Return lifecycle class and short reason for reports."""
    reason = forbidden_reason(column)
    if reason:
        if any(token in normalize_column(column) for token in ("mfe", "mae", "result", "profit", "exit", "future")):
            return "LEAKED", reason
        return "DYNAMIC", reason
    if column in ALLOWED_FEATURE_COLUMNS or column.endswith(ENTRY_SUFFIX):
        return "SAFE", "captured/frozen at entry"
    if column in KEY_OR_META_COLUMNS:
        return "SAFE_META", "identifier/timestamp, not an optimizer feature"
    return "SUSPECT", "not explicitly classified as causal"


def parse_timestamp(value) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def audit_timestamp_order(rows: Iterable[dict]) -> None:
    violations: list[str] = []
    for i, row in enumerate(rows, 1):
        feature_ts = parse_timestamp(row.get("feature_timestamp_utc"))
        entry_ts = parse_timestamp(row.get("entry_timestamp_utc"))
        if feature_ts and entry_ts and feature_ts > entry_ts:
            violations.append(
                f"row {i} fecha={row.get('fecha', '')} feature_timestamp_utc={feature_ts.isoformat()} "
                f"> entry_timestamp_utc={entry_ts.isoformat()}"
            )
    if violations:
        raise RuntimeError("Feature timestamp look-ahead detected:\n" + "\n".join(violations[:20]))
