# Edge Optimization Fast Report

Generated: 2026-07-11 23:46:41

Source causal dataset: `outputs\causal_dataset_20260711_234544`

Input rows: 564. Joined executed trades optimized: 564.



## Leakage Guard

`audit_feature_columns()` passed. The optimizer used only explicit causal aliases ending in `_AtEntry`; outcomes (`MFE`, `MAE`, `result_ticks`, exits, final CVD) were loaded only as labels for TP/SL replay.



## Recommended Robust Candidate

`regime=OR_large AND score>=8 | TP=100 SL=60`

| trades | wr | pf | expectancy | profit | dd | avg_mfe | avg_mae | avg_rr | std | max_w_streak | max_l_streak |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 144 | 64.58 | 1.96 | 10.30 | 1483.00 | 140.00 | 25.14 | 18.47 | 1.05 | 34.31 | 16 | 4 |



## Dynamic Contracts Requested: likely=4, middle=3, less likely=1

Selected sizing: `top 10% -> 4c | mid -> 3c | bottom 10% -> 1c`. High score cutoff `9.00`, low score cutoff `8.00`.

| trades | wr | pf | expectancy | profit | dd | std | max_w_streak | max_l_streak |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 144 | 64.58 | 2.47 | 101.08 | 14555.00 | 1200.00 | 323.44 | 16 | 4 |

| rule | high_cut | low_cut | trades | profit_usd | expectancy_usd | dd_usd | pf | test_expectancy_usd | test_dd_usd | avg_contracts | c1 | c3 | c4 | risk_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| top 10% -> 4c \| mid -> 3c \| bottom 10% -> 1c | 9.00 | 8.00 | 144 | 14555.00 | 101.08 | 1200.00 | 2.47 | 117.12 | 1200.00 | 1.44 | 123 | 0 | 21 | 0.87 |
| top 10% -> 4c \| mid -> 3c \| bottom 20% -> 1c | 9.00 | 8.00 | 144 | 14555.00 | 101.08 | 1200.00 | 2.47 | 117.12 | 1200.00 | 1.44 | 123 | 0 | 21 | 0.87 |
| top 10% -> 4c \| mid -> 3c \| bottom 30% -> 1c | 9.00 | 8.00 | 144 | 14555.00 | 101.08 | 1200.00 | 2.47 | 117.12 | 1200.00 | 1.44 | 123 | 0 | 21 | 0.87 |
| top 10% -> 4c \| mid -> 3c \| bottom 40% -> 1c | 9.00 | 8.00 | 144 | 14555.00 | 101.08 | 1200.00 | 2.47 | 117.12 | 1200.00 | 1.44 | 123 | 0 | 21 | 0.87 |
| top 20% -> 4c \| mid -> 3c \| bottom 10% -> 1c | 8.00 | 8.00 | 144 | 14555.00 | 101.08 | 1200.00 | 2.47 | 117.12 | 1200.00 | 1.44 | 123 | 0 | 21 | 0.87 |
| top 20% -> 4c \| mid -> 3c \| bottom 20% -> 1c | 8.00 | 8.00 | 144 | 14555.00 | 101.08 | 1200.00 | 2.47 | 117.12 | 1200.00 | 1.44 | 123 | 0 | 21 | 0.87 |
| top 20% -> 4c \| mid -> 3c \| bottom 30% -> 1c | 8.00 | 8.00 | 144 | 14555.00 | 101.08 | 1200.00 | 2.47 | 117.12 | 1200.00 | 1.44 | 123 | 0 | 21 | 0.87 |
| top 20% -> 4c \| mid -> 3c \| bottom 40% -> 1c | 8.00 | 8.00 | 144 | 14555.00 | 101.08 | 1200.00 | 2.47 | 117.12 | 1200.00 | 1.44 | 123 | 0 | 21 | 0.87 |
| top 30% -> 4c \| mid -> 3c \| bottom 10% -> 1c | 8.00 | 8.00 | 144 | 14555.00 | 101.08 | 1200.00 | 2.47 | 117.12 | 1200.00 | 1.44 | 123 | 0 | 21 | 0.87 |
| top 30% -> 4c \| mid -> 3c \| bottom 20% -> 1c | 8.00 | 8.00 | 144 | 14555.00 | 101.08 | 1200.00 | 2.47 | 117.12 | 1200.00 | 1.44 | 123 | 0 | 21 | 0.87 |



## Top Robust Candidates

| setup | trades | wr | pf | expectancy | profit | dd | test_pf | test_exp | active_months | monthly_pf_median | bad_months_pf_lt_1 | robust_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| regime=OR_large AND score>=8 \| TP=100 SL=60 | 144 | 64.58 | 1.96 | 10.30 | 1483.00 | 140.00 | 2.29 | 13.68 | 32 | 0.80 | 12 | 72.27 |
| regime=OR_large AND score>=8 \| TP=120 SL=60 | 144 | 64.58 | 1.96 | 10.30 | 1483.00 | 140.00 | 2.29 | 13.68 | 32 | 0.80 | 12 | 72.27 |
| regime=OR_large AND score>=8 \| TP=150 SL=60 | 144 | 64.58 | 1.96 | 10.30 | 1483.00 | 140.00 | 2.29 | 13.68 | 32 | 0.80 | 12 | 72.27 |
| regime=OR_large AND score>=8 \| TP=200 SL=60 | 144 | 64.58 | 1.96 | 10.30 | 1483.00 | 140.00 | 2.29 | 13.68 | 32 | 0.80 | 12 | 72.27 |
| regime=OR_large AND score>=8 \| TP=50 SL=100 | 144 | 65.28 | 1.97 | 10.01 | 1442.00 | 124.00 | 2.35 | 13.20 | 32 | 0.76 | 11 | 72.17 |
| regime=OR_large AND score>=8 \| TP=100 SL=70 | 144 | 64.58 | 1.95 | 10.26 | 1477.00 | 146.00 | 2.27 | 13.60 | 32 | 0.80 | 12 | 71.55 |
| regime=OR_large AND score>=8 \| TP=120 SL=70 | 144 | 64.58 | 1.95 | 10.26 | 1477.00 | 146.00 | 2.27 | 13.60 | 32 | 0.80 | 12 | 71.55 |
| regime=OR_large AND score>=8 \| TP=150 SL=70 | 144 | 64.58 | 1.95 | 10.26 | 1477.00 | 146.00 | 2.27 | 13.60 | 32 | 0.80 | 12 | 71.55 |
| regime=OR_large AND score>=8 \| TP=200 SL=70 | 144 | 64.58 | 1.95 | 10.26 | 1477.00 | 146.00 | 2.27 | 13.60 | 32 | 0.80 | 12 | 71.55 |
| regime=OR_large AND score>=8 \| TP=80 SL=60 | 144 | 64.58 | 1.95 | 10.22 | 1472.00 | 140.00 | 2.28 | 13.54 | 32 | 0.80 | 12 | 71.36 |
| regime=OR_large AND score>=8 \| TP=80 SL=70 | 144 | 64.58 | 1.94 | 10.18 | 1466.00 | 146.00 | 2.26 | 13.46 | 32 | 0.80 | 12 | 70.64 |
| regime=OR_large AND score>=8 \| TP=60 SL=60 | 144 | 64.58 | 1.94 | 10.13 | 1459.00 | 140.00 | 2.26 | 13.32 | 32 | 0.80 | 12 | 70.46 |
| regime=OR_large AND score>=8 \| TP=100 SL=80 | 144 | 64.58 | 1.94 | 10.19 | 1467.00 | 156.00 | 2.25 | 13.47 | 32 | 0.77 | 12 | 70.34 |
| regime=OR_large AND score>=8 \| TP=120 SL=80 | 144 | 64.58 | 1.94 | 10.19 | 1467.00 | 156.00 | 2.25 | 13.47 | 32 | 0.77 | 12 | 70.34 |
| regime=OR_large AND score>=8 \| TP=150 SL=80 | 144 | 64.58 | 1.94 | 10.19 | 1467.00 | 156.00 | 2.25 | 13.47 | 32 | 0.77 | 12 | 70.34 |
| regime=OR_large AND score>=8 \| TP=200 SL=80 | 144 | 64.58 | 1.94 | 10.19 | 1467.00 | 156.00 | 2.25 | 13.47 | 32 | 0.77 | 12 | 70.34 |
| regime=OR_large AND score>=8 \| actual | 144 | 64.58 | 1.93 | 10.18 | 1466.00 | 157.00 | 2.25 | 13.46 | 32 | 0.76 | 12 | 70.22 |
| regime=OR_large AND score>=8 \| TP=100 SL=100 | 144 | 64.58 | 1.93 | 10.18 | 1466.00 | 157.00 | 2.25 | 13.46 | 32 | 0.76 | 12 | 70.22 |
| regime=OR_large AND score>=8 \| TP=120 SL=100 | 144 | 64.58 | 1.93 | 10.18 | 1466.00 | 157.00 | 2.25 | 13.46 | 32 | 0.76 | 12 | 70.22 |
| regime=OR_large AND score>=8 \| TP=150 SL=100 | 144 | 64.58 | 1.93 | 10.18 | 1466.00 | 157.00 | 2.25 | 13.46 | 32 | 0.76 | 12 | 70.22 |



## Top Naive Candidates (Overfit Risk)

| setup | trades | wr | pf | expectancy | profit | dd | test_pf | test_exp | active_months | monthly_pf_median | bad_months_pf_lt_1 | robust_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aplus_speed=TRUE \| TP=60 SL=40 | 70 | 67.14 | 1.96 | 12.57 | 880.00 | 150.00 | 3.09 | 20.30 | 27 | 0.75 | 9 | 55.26 |
| aplus_speed=TRUE \| TP=80 SL=40 | 70 | 67.14 | 1.96 | 12.57 | 880.00 | 150.00 | 3.09 | 20.30 | 27 | 0.75 | 9 | 55.26 |
| aplus_speed=TRUE \| TP=100 SL=40 | 70 | 67.14 | 1.96 | 12.57 | 880.00 | 150.00 | 3.09 | 20.30 | 27 | 0.75 | 9 | 55.26 |
| aplus_speed=TRUE \| TP=120 SL=40 | 70 | 67.14 | 1.96 | 12.57 | 880.00 | 150.00 | 3.09 | 20.30 | 27 | 0.75 | 9 | 55.26 |
| aplus_speed=TRUE \| TP=150 SL=40 | 70 | 67.14 | 1.96 | 12.57 | 880.00 | 150.00 | 3.09 | 20.30 | 27 | 0.75 | 9 | 55.26 |
| aplus_speed=TRUE \| TP=200 SL=40 | 70 | 67.14 | 1.96 | 12.57 | 880.00 | 150.00 | 3.09 | 20.30 | 27 | 0.75 | 9 | 55.26 |
| speed=POTENTIAL_RUNNER \| TP=60 SL=40 | 68 | 66.18 | 1.86 | 11.62 | 790.00 | 240.00 | 3.09 | 20.30 | 27 | 0.75 | 9 | 42.93 |
| speed=POTENTIAL_RUNNER \| TP=80 SL=40 | 68 | 66.18 | 1.86 | 11.62 | 790.00 | 240.00 | 3.09 | 20.30 | 27 | 0.75 | 9 | 42.93 |
| speed=POTENTIAL_RUNNER \| TP=100 SL=40 | 68 | 66.18 | 1.86 | 11.62 | 790.00 | 240.00 | 3.09 | 20.30 | 27 | 0.75 | 9 | 42.93 |
| speed=POTENTIAL_RUNNER \| TP=120 SL=40 | 68 | 66.18 | 1.86 | 11.62 | 790.00 | 240.00 | 3.09 | 20.30 | 27 | 0.75 | 9 | 42.93 |
| speed=POTENTIAL_RUNNER \| TP=150 SL=40 | 68 | 66.18 | 1.86 | 11.62 | 790.00 | 240.00 | 3.09 | 20.30 | 27 | 0.75 | 9 | 42.93 |
| speed=POTENTIAL_RUNNER \| TP=200 SL=40 | 68 | 66.18 | 1.86 | 11.62 | 790.00 | 240.00 | 3.09 | 20.30 | 27 | 0.75 | 9 | 42.93 |
| aplus_speed=TRUE \| TP=50 SL=40 | 70 | 67.14 | 1.86 | 11.29 | 790.00 | 160.00 | 2.84 | 17.88 | 27 | 0.75 | 8 | 46.00 |
| aplus_speed=TRUE \| TP=60 SL=50 | 70 | 68.57 | 1.69 | 10.86 | 760.00 | 270.00 | 3.00 | 21.21 | 27 | 0.60 | 9 | 33.30 |
| aplus_speed=TRUE \| TP=80 SL=50 | 70 | 68.57 | 1.69 | 10.86 | 760.00 | 270.00 | 3.00 | 21.21 | 27 | 0.60 | 9 | 33.30 |
| aplus_speed=TRUE \| TP=100 SL=50 | 70 | 68.57 | 1.69 | 10.86 | 760.00 | 270.00 | 3.00 | 21.21 | 27 | 0.60 | 9 | 33.30 |
| aplus_speed=TRUE \| TP=120 SL=50 | 70 | 68.57 | 1.69 | 10.86 | 760.00 | 270.00 | 3.00 | 21.21 | 27 | 0.60 | 9 | 33.30 |
| aplus_speed=TRUE \| TP=150 SL=50 | 70 | 68.57 | 1.69 | 10.86 | 760.00 | 270.00 | 3.00 | 21.21 | 27 | 0.60 | 9 | 33.30 |
| aplus_speed=TRUE \| TP=200 SL=50 | 70 | 68.57 | 1.69 | 10.86 | 760.00 | 270.00 | 3.00 | 21.21 | 27 | 0.60 | 9 | 33.30 |
| aplus_speed=TRUE \| TP=60 SL=30 | 70 | 60.00 | 1.89 | 10.71 | 750.00 | 120.00 | 2.64 | 16.36 | 27 | 1.00 | 6 | 50.07 |



## Monte Carlo

Ticks, fixed result distribution:

| sims | horizon_trades | final_mean | dd_mean | dd_95 | dd_99 | loss_streak_mean | p_loss_streak_3 | p_loss_streak_5 | p_loss_streak_8 | p_loss_streak_10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10000 | 144 | 1525.26 | 161.80 | 240.00 | 290.00 | 3.83 | 97.42 | 14.92 | 0.02 | 0.00 |

USD, dynamic 1/3/4 contracts:

| sims | horizon_trades | final_mean | dd_mean | dd_95 | dd_99 | loss_streak_mean | p_loss_streak_3 | p_loss_streak_5 | p_loss_streak_8 | p_loss_streak_10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10000 | 144 | 14859.30 | 1345.98 | 1990.00 | 2400.00 | 3.83 | 97.42 | 14.92 | 0.02 | 0.00 |



## Lucid 150k, Dynamic 1/3/4 Sizing

| pass_pct_3mo | bust_pct_3mo | timeout_pct_3mo | avg_trades_to_pass | dd_95_usd |
| --- | --- | --- | --- | --- |
| 0.00 | 0.00 | 100.00 |  | 1200.00 |



## Notes

- TP/SL simulation uses observed MFE/MAE. If both TP and SL are reachable, SL wins. This is conservative.

- Dynamic sizing uses `score total` as the probability proxy. It does not use future MFE/MAE.

- Profile-shape buckets P/b/D/Trend/Tree are not optimized because the v11 files do not populate reliable profile-shape labels.