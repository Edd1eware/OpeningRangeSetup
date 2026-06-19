from visual_replay_test_common import (
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

        duration_seconds = to_float(timeline[-1].get("Seconds_From_Entry"))
        if duration_seconds is None or duration_seconds >= 1:
            continue

        candidates.append(
            {
                "Fecha": date_iso,
                "Entrada_NY": trade.get("EntryTime_NY", ""),
                "Salida_NY": trade.get("ExitTime_NY", ""),
                "Duracion_timeline_ms": round(duration_seconds * 1000, 3),
                "Lado": trade.get("Side", ""),
                "Resultado_exportado": trade.get("Result_Label", ""),
                "Entry": trade.get("Entry_price", ""),
                "SL": trade.get("SL_price", ""),
                "TP": trade.get("TP_price", ""),
            }
        )

    return candidates


run_visual_dates(
    "test_dates_zero_seconds",
    find_candidates(),
    [
        "Duración subsegundo válida",
        "Duración incorrecta",
        "Movimiento ocurrió pero no pude cronometrar",
        "Datos no cargaron",
    ],
    (
        "Valida trades cuya duración medida fue menor a un segundo. La nueva DLL "
        "exporta EntryTime_NY_Milliseconds, ExitTime_NY_Milliseconds y "
        "Trade_Duration_Milliseconds."
    ),
)
