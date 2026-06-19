from visual_replay_test_common import discover_trade_rows, run_visual_dates, to_float


def find_candidates():
    candidates = []

    for trade in discover_trade_rows():
        imbalance_count = to_float(trade.get("Imbalance_Count"))
        buy_count = to_float(trade.get("Buy_Imbalance_Count"))
        sell_count = to_float(trade.get("Sell_Imbalance_Count"))

        if not (
            (imbalance_count is not None and imbalance_count > 0)
            or (buy_count is not None and buy_count > 0)
            or (sell_count is not None and sell_count > 0)
        ):
            continue

        candidates.append(
            {
                "Fecha": trade.get("fecha", ""),
                "Entrada_NY": trade.get("EntryTime_NY", ""),
                "Lado_trade": trade.get("Side", ""),
                "Signal_Source": trade.get("Signal_Source", ""),
                "Imbalance_Count": trade.get("Imbalance_Count", ""),
                "Buy_Imbalance_Count": trade.get("Buy_Imbalance_Count", ""),
                "Sell_Imbalance_Count": trade.get("Sell_Imbalance_Count", ""),
                "Imbalance_Group_3": trade.get("Imbalance_Group_3", ""),
                "Imbalance_Group_Price": trade.get("Imbalance_Group_Price", ""),
                "Resultado": trade.get("Result_Label", ""),
            }
        )

    return candidates


run_visual_dates(
    "Imbalance_Count_test",
    find_candidates(),
    [
        "Conteo correcto",
        "Falso positivo",
        "Faltan imbalances visibles",
        "No pude determinar",
        "Datos no cargaron",
    ],
    (
        "Compara los imbalances diagonales visibles con los conteos exportados. "
        "La nueva DLL separa Buy_Imbalance_Count, Sell_Imbalance_Count y el conteo "
        "del lado de ejecución."
    ),
)
