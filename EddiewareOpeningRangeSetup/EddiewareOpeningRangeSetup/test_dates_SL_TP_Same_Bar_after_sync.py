from visual_replay_test_common_after_sync import (
    discover_trade_rows,
    read_csv_rows,
    run_visual_dates,
    timeline_path,
    to_float,
)


def find_candidates():
    candidates = []

    for trade in discover_trade_rows():
        date_iso = trade["fecha"]
        path = timeline_path(date_iso)
        if not path.exists():
            continue

        timeline = read_csv_rows(path)
        if not timeline:
            continue

        sl_ticks = to_float(trade.get("SL_ticks"))
        tp_ticks = to_float(trade.get("TP_ticks"))
        mae_ticks = to_float(trade.get("MAE_ticks"))
        mfe_ticks = to_float(trade.get("MFE_ticks"))
        same_bar = timeline[0].get("Bar") == timeline[-1].get("Bar")

        if (
            same_bar
            and sl_ticks is not None
            and tp_ticks is not None
            and mae_ticks is not None
            and mfe_ticks is not None
            and mae_ticks >= sl_ticks
            and mfe_ticks >= tp_ticks
        ):
            candidates.append(
                {
                    "Fecha": date_iso,
                    "Entrada_NY": trade.get("EntryTime_NY", ""),
                    "Salida_NY": trade.get("ExitTime_NY", ""),
                    "Lado": trade.get("Side", ""),
                    "Resultado_exportado": trade.get("Result_Label", ""),
                    "Entry": trade.get("Entry_price", ""),
                    "SL": trade.get("SL_price", ""),
                    "TP": trade.get("TP_price", ""),
                    "MAE_ticks": trade.get("MAE_ticks", ""),
                    "MFE_ticks": trade.get("MFE_ticks", ""),
                    "Diagnostico": "TP y SL alcanzables en la misma actualización agregada",
                }
            )

    return candidates


run_visual_dates(
    "test_dates_SL_TP_Same_Bar",
    find_candidates(),
    ["TP primero", "SL primero", "No pude determinar", "Datos no cargaron"],
    (
        "Valida cuál nivel se negoció primero cuando el rango observado contiene "
        "tanto TP como SL. El código histórico conserva TP primero por compatibilidad, "
        "pero OHLC no puede resolver el orden intrabar."
    ),
)
