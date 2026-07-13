# Causal Section Walk-Forward

Generated: 2026-07-11 23:55:32
Causal dataset: `outputs\causal_dataset_20260711_234544`

## Rule

Selection is made only with prior years. The next year is out-of-sample and is not used to repair the model.

## Combined OOS

| trades | months | trades_per_month | wr | pf | expectancy | profit | dd | max_w_streak | max_l_streak |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 302 | 30 | 10.07 | 50.66 | 1.26 | 3.16 | 955.00 | 414.00 | 6 | 9 |

Gate to launch full 2022-2026 replay: FAIL

## Folds

| test_year | filter | tp | sl | train_trades | train_pf | train_exp | train_bad_months | oos_trades | oos_wr | oos_pf | oos_exp | oos_profit | oos_dd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2023 | score>=6 AND OR<=160 | 80 | 30 | 116 | 1.45 | 5.25 | 1 | 122 | 46.72 | 1.11 | 1.27 | 155.00 | 414.00 |
| 2024 | score>=8 AND OR>=100 | 60 | 30 | 120 | 1.42 | 4.85 | 3 | 50 | 48.00 | 1.07 | 0.84 | 42.00 | 134.00 |
| 2025 | score>=7 AND OR<=160 | 60 | 30 | 290 | 1.29 | 3.39 | 7 | 70 | 52.86 | 1.44 | 5.13 | 359.00 | 110.00 |
| 2026 | OR>=140 | 100 | 60 | 133 | 1.80 | 8.94 | 9 | 60 | 58.33 | 1.45 | 6.65 | 399.00 | 155.00 |

## Selected Pattern Stability

- `score>=6 AND OR<=160`: 1 fold(s)
- `score>=8 AND OR>=100`: 1 fold(s)
- `score>=7 AND OR<=160`: 1 fold(s)
- `OR>=140`: 1 fold(s)

## First Replay Section

Use the earliest section first, then scale only if the fresh v12 causal files agree with the offline expectation.

| section | from_date | to_date | sessions_with_trade_in_legacy |
| --- | --- | --- | --- |
| 2022-Q2 | 2022-04-04 | 2022-06-30 | 59 |
| 2022-Q3 | 2022-07-01 | 2022-09-30 | 59 |
| 2022-Q4 | 2022-10-03 | 2022-11-04 | 24 |
| 2023-Q1 | 2023-03-14 | 2023-03-30 | 10 |
| 2023-Q2 | 2023-04-06 | 2023-06-30 | 47 |
| 2023-Q3 | 2023-07-06 | 2023-09-28 | 48 |
| 2023-Q4 | 2023-10-02 | 2023-11-02 | 20 |
| 2024-Q1 | 2024-03-11 | 2024-03-28 | 12 |