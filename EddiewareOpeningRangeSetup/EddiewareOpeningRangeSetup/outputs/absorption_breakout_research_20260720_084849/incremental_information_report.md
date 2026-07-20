# Incremental information report — v27

Baseline: intensidad del burst, delta, velocidad, aceleración, eficiencia y perfil existentes.

Las familias nuevas se evalúan sólo fuera de muestra. Este archivo no autoriza filtros ni thresholds.

## Cobertura por familia

| family | variables | variable_count | mean_coverage_pct | best_abs_cliffs_delta | robust_candidate_count |
| --- | --- | --- | --- | --- | --- |
| ACCEPTANCE_REJECTION | PreBurst_Acceptance_Dwell_Ratio_5s/PreBurst_Reclaim_Count_10s/PreEntry_Acceptance_Dwell_Ratio_AtEntry/PreEntry_Reclaim_Count_AtEntry/PreEntry_Rejection_Speed_TPS_AtEntry | 5 | 100.0 | 0.11606391925988226 | 0 |
| AUCTION_CONTEXT | OR_WidthTicks/Dist_OR_High_Ticks/Dist_OR_Low_Ticks/Dist_VWAP_Ticks/Dist_POC_Ticks/Profile_Std_Ticks/Profile_Skewness/Profile_Excess_Kurtosis/Profile_Normalized_Entropy/Profile_Concentration/Profile_Effective_Nodes/Profile_Local_Maxima_Count/Profile_Position_Percentile/POC_Migration_Ticks/GapFill_Seconds_60/Directional_OR_Extension_Ticks_AtEntry/Directional_VWAP_Distance_Ticks_AtEntry/Nearest_OR_Edge_Distance_Ticks_AtEntry/Body_OR_Ratio_AtEntry/Prior_Closed_ATR3_Ticks_AtEntry/Prior_Closed_ATR5_Ticks_AtEntry/Nearest_OR_Edge_Acceptance_Ratio3_AtEntry/Detector_Publish_Delay_Milliseconds/directional_vwap_distance/directional_poc_distance/profile_confluence_4t | 26 | 96.34197324414716 | 0.4087468460891506 | 0 |
| BURST_INTENSITY | Delta1s/Delta2s/Delta3s/Delta5s/Delta10s/PeakPositiveDelta/PeakNegativeDelta/DeltaChange1s/DeltaChangeZScore/DeltaPercentile/BuySellRatio/TradesPerSecond/ContractsPerSecond/Velocity1s/Velocity3s/Velocity5s/Acceleration1s/Acceleration3s/TicksPerSecond/CumulativeDeltaWindow/Dist_VAH_Ticks/Dist_VAL_Ticks/Dist_HVN_Ticks/Dist_LVN_Ticks/PreBurst_Rotation_Index_10s/PreBurst_Local_Entropy_10s/PreBurst_Path_Efficiency_10s/PreBurst_Impulse_Survival_Seconds/PreBurst_Impulse_Decay_Slope_5s/Realized_Volatility_10s_Ticks/Realized_Volatility_30s_Ticks/Realized_Volatility_60s_Ticks/Short_Long_Volatility_Ratio/Observation_Coverage_60/range/Body_AtEntry/Volume_AtEntry/Delta_AtEntry/Cumulative_Delta_AtEntry/Previous_Volume_AtEntry/Previous_Delta_AtEntry/Delta_Change_AtEntry/BreakOut_TICKS_PER_SEC_AtEntry/Score_AtEntry/Buy_Imbalance_Count_AtEntry/Sell_Imbalance_Count_AtEntry/Seconds_From_Open_AtEntry/Signed_Delta_Share_AtEntry/Signed_Previous_Delta_Share_AtEntry/PreEntry_Directional_Efficiency3_AtEntry/PreEntry_Directional_Delta_Share3_AtEntry/PreEntry_Range_Compression3_AtEntry/PreEntry_Volume_Climax_Ratio_AtEntry/Directional_CLV_AtEntry/PreEntry_Rotation_Index_AtEntry/PreEntry_Local_Entropy_AtEntry/PreEntry_Path_Efficiency_AtEntry/signed_delta_1s/signed_delta_change_1s/signed_velocity_1s/signed_velocity_3s/signed_acceleration_1s/price_impact_per_100_contracts/absorption_pressure_1s/delta_share_of_volume/mean_trade_size/delta_persistence_1_3/delta_persistence_3_5/direction_consistency/velocity_consistency/acceleration_velocity_ratio/burst_efficiency_score/liquidity_absorption_score | 73 | 98.63013698630137 | 0.2910008410428932 | 0 |
| CROSSING_ANATOMY | Pre_Approach_Distance_Ticks/Pre_Approach_Velocity_TPS/Pre_Approach_Pause_Seconds | 3 | 100.0 | 0.32127838519764507 | 0 |
| EFFORT_RESULT | PreBurst_Price_Per_Delta_3s/PreBurst_Price_Per_Volume_3s/PreEntry_Price_Per_Delta_AtEntry/PreEntry_Price_Per_Volume_AtEntry | 4 | 100.0 | 0.2060555088309504 | 0 |
| EVENT_DEPENDENCE | Burst_Index_In_Episode/Seconds_Since_Prior_Burst/Liquidity_Burst_Index_In_Episode/Liquidity_Burst_Seconds_Since_Prior_Burst | 4 | 52.44565217391304 | 0.0 | 0 |
| EXECUTION_QUALITY | Signal_To_Entry_Latency_Milliseconds/Detector_Publish_To_Entry_Latency_Milliseconds | 2 | 100.0 | 0.23380992430613962 | 0 |
| FLOW_PERSISTENCE | Flow_0_1_DirectionalNetDelta/Flow_1_3_DirectionalNetDelta/Flow_3_5_DirectionalNetDelta/Flow_0_1_GrossAggressive/Flow_1_3_GrossAggressive/Flow_3_5_GrossAggressive/Flow_0_1_CounterflowShare/Flow_1_3_CounterflowShare/Flow_3_5_CounterflowShare/Flow_0_1_DirectionalVelocityTPS/Flow_1_3_DirectionalVelocityTPS/Flow_3_5_DirectionalVelocityTPS/Flow_0_1_TicksPerAggressiveContract/Velocity_Retention_1_3/Velocity_Retention_3_5/Delta_Retention_1_3/Delta_Retention_3_5/Flow_Aligned_Segment_Count/Flow_Conflict_Segment_Count/flow_price_alignment | 20 | 98.8858695652174 | 0.29857022708158115 | 0 |
| LEVEL_MEMORY | Prior_Level_Touches_60s/Prior_Full_Crosses_60s/Prior_Volume_At_Level_Band_60s/Time_Since_Last_Prior_Level_Touch_Seconds/Nearest_OR_Edge_Retest_Count_AtEntry | 5 | 96.52173913043478 | 0.2396972245584525 | 0 |

## Métricas de modelos auditados

| model | split | status | n | balanced_accuracy | roc_auc | confusion_matrix |
| --- | --- | --- | --- | --- | --- | --- |
| logistic | validation | OK | 25 | 0.5441176470588236 | 0.5147058823529412 | [[10, 7], [4, 4]] |
| logistic | holdout | OK | 29 | 0.29166666666666663 | 0.23888888888888887 | [[5, 15], [6, 3]] |
| decision_tree | validation | OK | 25 | 0.4007352941176471 | 0.3639705882352941 | [[3, 14], [3, 5]] |
| decision_tree | holdout | OK | 29 | 0.4388888888888889 | 0.6222222222222223 | [[2, 18], [2, 7]] |
| random_forest | validation | OK | 25 | 0.6397058823529411 | 0.5588235294117647 | [[9, 8], [2, 6]] |
| random_forest | holdout | OK | 29 | 0.3833333333333333 | 0.2777777777777778 | [[2, 18], [3, 6]] |
| catboost | validation | OK | 25 | 0.5477941176470589 | 0.5073529411764706 | [[8, 9], [3, 5]] |
| catboost | holdout | OK | 29 | 0.4027777777777778 | 0.32222222222222224 | [[5, 15], [4, 5]] |
