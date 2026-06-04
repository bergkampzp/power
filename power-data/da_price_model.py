"""
DA Price Prediction Model (日前电价预测)
========================================
Target  : 漫湾厂.500kV 次日日前节点电价 (24h × 96 periods)
Features: 75+ features from dbt feat_da_features table
Models  : P0-DA (GBR) / P3-DA (Spread: DA[D+1]-DA[D]) / P4-DA (Hybrid)
Backtest: Walk-forward, train on 2025-06 ~ 2026-02, test on 2026-03

Data source: PostgreSQL warehouse (via dbt feat_da_features)
MLflow tracking: http://localhost:5002
"""

import os
import warnings
import numpy as np
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb
import xgboost as xgb
import mlflow
import mlflow.sklearn

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
PG_CONN = dict(host="localhost", port=5433, user="postgres",
               password="postgres", dbname="warehouse")
MLFLOW_URI = "http://localhost:5002"
BACKTEST_START = "20260301"
BACKTEST_END   = "20260322"
NODE = "漫湾厂.500kV#1M"

FEATURE_COLS = [
    # Time (26)
    "hour_feat", "dayofweek", "day", "month", "is_weekend",
    "hour_sin", "hour_cos", "dow_sin", "dow_cos",
    "month_sin", "month_cos", "woy_sin", "woy_cos", "doy_sin", "doy_cos",
    "is_wet_season", "is_transition", "q1", "q2", "q3", "q4",
    "day_of_year", "week_of_year", "wet_x_hour", "is_zero_risk_hour",
    # DA auto-regression (12)
    "da_lag_1d", "da_lag_2d", "da_lag_3d", "da_lag_7d",
    "da_ma_3d", "da_ma_5d", "da_ma_7d", "da_std_3d", "da_std_7d",
    "da_momentum_1d", "da_wow_change", "da_grid_lag_1d",
    # RT reference (6)
    "rt_lag_1d", "rt_lag_2d", "rt_lag_7d", "rt_ma_3d",
    "rt_da_spread_lag1", "node_grid_spread_lag1",
    # Load/renew/hydro lags (5)
    "load_lag_1d", "load_lag_2d", "renew_lag_1d", "renew_lag_2d", "hydro_lag_1d",
    # Supply-demand balance (8)
    "gap", "fc_gap", "gap_lag_1d", "gap_lag_2d",
    "renew_fc_share", "reserve_ratio", "flow_to_cap", "renew_fc_vs_lag",
    # Forecast features (5)
    "renew_fc", "load_fc", "hydro_fc_avg", "gen_fc", "load_fc_vs_lag",
    # Grid operations (7)
    "chan_lag1d", "maint_lag1d", "reserve_up_lag1d",
    "n_sections", "avg_limit", "maint_count", "zero_yesterday",
    # Prev-day aggregates (8)
    "prevday_da_avg", "prevday_da_max", "prevday_da_min", "prevday_da_std",
    "prevday_rt_avg", "prevday_load_avg", "da_vs_ma7_ratio", "prevday_price_range",
]
TARGET_COL = "target_da_price"


# ─────────────────────────────────────────────────────────────────────────────
# Data Loading
# ─────────────────────────────────────────────────────────────────────────────
def load_features() -> pd.DataFrame:
    conn = psycopg2.connect(**PG_CONN)
    df = pd.read_sql("""
        SELECT date_key, hour, target_da_price,
               """ + ", ".join(FEATURE_COLS) + """
        FROM feat_da_features
        WHERE date_key >= '20250601'
        ORDER BY date_key, hour
    """, conn)
    conn.close()
    df = df.fillna(0)
    print(f"Loaded {len(df)} rows, {df['date_key'].nunique()} days")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Sample weighting: time decay + season match
# ─────────────────────────────────────────────────────────────────────────────
def compute_weights(train_df: pd.DataFrame, pred_date: str) -> np.ndarray:
    pred_dt = datetime.strptime(pred_date, "%Y%m%d")
    days_ago = train_df["date_key"].apply(
        lambda d: (pred_dt - datetime.strptime(d, "%Y%m%d")).days
    )
    # Time decay: half-life 60 days
    time_w = np.exp(-np.log(2) * days_ago / 60)
    # Season match: same season gets 2x, opposite gets 0.5x
    pred_month = pred_dt.month
    is_wet = (5 <= pred_month <= 10)
    train_wet = train_df["is_wet_season"].values.astype(bool)
    season_w = np.where(train_wet == is_wet, 2.0, 0.5)
    w = time_w * season_w
    return w / w.sum() * len(w)


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────
def build_p0_model():
    """P0-DA: GBR direct DA price prediction"""
    return GradientBoostingRegressor(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        subsample=0.85, min_samples_leaf=3, random_state=42
    )


def build_p3_spread_models():
    """P3-DA: Predict DA[D+1] - DA[D] spread, then add DA[D]"""
    gbr = GradientBoostingRegressor(
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.85, random_state=42
    )
    lgbm = lgb.LGBMRegressor(
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.85, verbose=-1, random_state=42
    )
    xgbm = xgb.XGBRegressor(
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.85, verbosity=0, random_state=42
    )
    return gbr, lgbm, xgbm


def anomaly_score(day_df: pd.DataFrame) -> float:
    """Compute anomaly score from D-1 signals (0-1 scale)"""
    score = 0.0
    da_prices = day_df["da_lag_1d"].values
    if len(da_prices) == 0:
        return 0.0
    spread = day_df["rt_da_spread_lag1"].values
    # Large RT-DA spread yesterday
    if np.abs(spread).mean() > 100:
        score += 0.3
    # High DA volatility yesterday
    if da_prices.std() > 150:
        score += 0.2
    # Big DA change from D-2 to D-1
    if np.abs(day_df["da_momentum_1d"].values).mean() > 80:
        score += 0.2
    # High renewable forecast share (zero-price risk)
    if day_df["renew_fc_share"].values.mean() > 0.6:
        score += 0.3
    return min(score, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward backtest
# ─────────────────────────────────────────────────────────────────────────────
def walk_forward_backtest(df: pd.DataFrame) -> pd.DataFrame:
    test_days = sorted([
        d for d in df["date_key"].unique()
        if BACKTEST_START <= d <= BACKTEST_END
    ])
    results = []

    for test_date in test_days:
        train_df = df[df["date_key"] < test_date].copy()
        test_df  = df[df["date_key"] == test_date].copy()

        if len(train_df) < 500 or len(test_df) == 0:
            continue

        X_train = train_df[FEATURE_COLS].values
        y_train = train_df[TARGET_COL].values
        X_test  = test_df[FEATURE_COLS].values
        y_test  = test_df[TARGET_COL].values

        # Filter training samples where target is valid
        valid_mask = y_train > 0
        X_train_v, y_train_v = X_train[valid_mask], y_train[valid_mask]
        train_df_v = train_df[valid_mask]

        weights = compute_weights(train_df_v, test_date)

        # ── P0-DA: GBR direct ──
        p0 = build_p0_model()
        p0.fit(X_train_v, y_train_v, sample_weight=weights)
        p0_pred = p0.predict(X_test)

        # ── P3-DA: Spread models ──
        # Spread target = DA[today] - DA[yesterday], using da_lag_1d as DA[yesterday]
        y_spread = y_train_v - train_df_v["da_lag_1d"].values
        gbr, lgbm, xgbm = build_p3_spread_models()
        gbr.fit(X_train_v, y_spread, sample_weight=weights)
        lgbm.fit(X_train_v, y_spread, sample_weight=weights)
        xgbm.fit(X_train_v, y_spread, sample_weight=weights)

        da_baseline = test_df["da_lag_1d"].values  # DA[D] = known at prediction time
        spread_pred = (
            0.35 * gbr.predict(X_test) +
            0.35 * lgbm.predict(X_test) +
            0.30 * xgbm.predict(X_test)
        )
        p3_pred = da_baseline + spread_pred

        # ── P4-DA: Hybrid adaptive ──
        a_score = anomaly_score(test_df)
        w_p3 = min(a_score * 0.8, 0.6)
        w_p0 = 1.0 - w_p3
        p4_pred = w_p0 * p0_pred + w_p3 * p3_pred

        # ── Metrics (non-zero actual only) ──
        nz_mask = y_test > 0
        for model_name, preds in [("P0_DA", p0_pred), ("P3_DA", p3_pred), ("P4_DA", p4_pred)]:
            if nz_mask.sum() > 0:
                mae  = mean_absolute_error(y_test[nz_mask], preds[nz_mask])
                rmse = np.sqrt(mean_squared_error(y_test[nz_mask], preds[nz_mask]))
                r2   = r2_score(y_test[nz_mask], preds[nz_mask])
            else:
                mae, rmse, r2 = 0, 0, 0

            results.append({
                "date": test_date,
                "model": model_name,
                "mae": round(mae, 2),
                "rmse": round(rmse, 2),
                "r2": round(r2, 4),
                "anomaly_score": round(a_score, 3),
                "w_p3": round(w_p3, 3),
                "n_hours": int(nz_mask.sum()),
                "preds": preds,
                "actuals": y_test,
                "hours": test_df["hour"].values,
            })
            print(f"  {test_date} {model_name}: MAE={mae:.1f}  RMSE={rmse:.1f}  R²={r2:.3f}  "
                  f"anomaly={a_score:.2f}")

    return pd.DataFrame(results)


# ─────────────────────────────────────────────────────────────────────────────
# Save predictions back to PostgreSQL for Metabase
# ─────────────────────────────────────────────────────────────────────────────
def save_predictions_to_pg(results_df: pd.DataFrame, model_name: str = "P4_DA"):
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()

    # Widen dashboard_predictions to support prediction_type + model_version
    cur.execute("""
        ALTER TABLE dashboard_predictions
        ADD COLUMN IF NOT EXISTS prediction_type VARCHAR(20) DEFAULT 'da_price',
        ADD COLUMN IF NOT EXISTS model_version VARCHAR(20);
    """)
    conn.commit()

    model_rows = results_df[results_df["model"] == model_name]
    inserted = 0
    for _, row in model_rows.iterrows():
        date_key = row["date"]
        for i, (h, pred, actual) in enumerate(zip(
                row["hours"], row["preds"], row["actuals"])):
            err = pred - actual
            cur.execute("""
                INSERT INTO dashboard_predictions
                  (date_key, hour, actual_price, predicted_price, error, abs_error, pct_error,
                   prediction_type, model_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (date_key, hour) DO UPDATE SET
                  predicted_price = EXCLUDED.predicted_price,
                  actual_price    = EXCLUDED.actual_price,
                  error           = EXCLUDED.error,
                  abs_error       = EXCLUDED.abs_error,
                  pct_error       = EXCLUDED.pct_error,
                  prediction_type = EXCLUDED.prediction_type,
                  model_version   = EXCLUDED.model_version
            """, (
                date_key, int(h), float(actual), float(pred),
                float(err), float(abs(err)),
                float(abs(err) / actual * 100) if actual > 0 else 0,
                "da_price", model_name
            ))
            inserted += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Saved {inserted} prediction rows to PostgreSQL")


# ─────────────────────────────────────────────────────────────────────────────
# MLflow logging
# ─────────────────────────────────────────────────────────────────────────────
def log_to_mlflow(results_df: pd.DataFrame):
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment("DA_Price_Prediction")

    for model_name in ["P0_DA", "P3_DA", "P4_DA"]:
        model_rows = results_df[results_df["model"] == model_name]
        if model_rows.empty:
            continue

        avg_mae  = model_rows["mae"].mean()
        avg_rmse = model_rows["rmse"].mean()
        avg_r2   = model_rows["r2"].mean()

        with mlflow.start_run(run_name=f"{model_name}_{datetime.now().strftime('%m%d_%H%M')}"):
            mlflow.log_param("model", model_name)
            mlflow.log_param("target", "da_price")
            mlflow.log_param("backtest_start", BACKTEST_START)
            mlflow.log_param("backtest_end", BACKTEST_END)
            mlflow.log_param("n_features", len(FEATURE_COLS))
            mlflow.log_param("node", NODE)

            mlflow.log_metric("avg_mae",  round(avg_mae, 2))
            mlflow.log_metric("avg_rmse", round(avg_rmse, 2))
            mlflow.log_metric("avg_r2",   round(avg_r2, 4))

            # Per-day metrics
            for _, row in model_rows.iterrows():
                step = int(row["date"][-2:])
                mlflow.log_metric(f"daily_mae",  row["mae"],  step=step)
                mlflow.log_metric(f"daily_r2",   row["r2"],   step=step)

            print(f"MLflow [{model_name}]: MAE={avg_mae:.2f}  RMSE={avg_rmse:.2f}  R²={avg_r2:.4f}")


# ─────────────────────────────────────────────────────────────────────────────
# Summary report
# ─────────────────────────────────────────────────────────────────────────────
def print_summary(results_df: pd.DataFrame):
    print("\n" + "="*70)
    print("DA PRICE PREDICTION BACKTEST SUMMARY  (2026-03-01 ~ 2026-03-22)")
    print("="*70)

    for model_name in ["P0_DA", "P3_DA", "P4_DA"]:
        rows = results_df[results_df["model"] == model_name]
        if rows.empty:
            continue
        print(f"\n{'─'*40}")
        print(f"  Model: {model_name}")
        print(f"  Days:  {len(rows)}")
        print(f"  MAE  (avg): {rows['mae'].mean():.2f} 元/MWh")
        print(f"  MAE  (min): {rows['mae'].min():.2f}")
        print(f"  MAE  (max): {rows['mae'].max():.2f}")
        print(f"  RMSE (avg): {rows['rmse'].mean():.2f}")
        print(f"  R²   (avg): {rows['r2'].mean():.4f}")

        print(f"\n  日期明细:")
        print(f"  {'日期':<12} {'MAE':>8} {'RMSE':>8} {'R²':>8} {'异常分':>8}")
        for _, r in rows.iterrows():
            grade = "✅" if r["mae"] < 40 else ("⚠️" if r["mae"] < 80 else "❌")
            print(f"  {r['date']:<12} {r['mae']:>8.1f} {r['rmse']:>8.1f} "
                  f"{r['r2']:>8.3f} {r['anomaly_score']:>8.3f} {grade}")

    print("\n" + "="*70)
    # Best model comparison
    summary = results_df.groupby("model")[["mae","rmse","r2"]].mean().round(3)
    print("\n模型对比（测试集均值）:")
    print(summary.to_string())
    print("="*70)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("="*70)
    print(f"DA Price Model Training  [{datetime.now().strftime('%Y-%m-%d %H:%M')}]")
    print(f"Target: 次日日前电价 (漫湾厂.500kV#1M)")
    print(f"Backtest: {BACKTEST_START} → {BACKTEST_END}")
    print("="*70)

    # 1. Load features from dbt/PostgreSQL
    print("\n[1/4] Loading features from PostgreSQL warehouse...")
    df = load_features()

    # Data stats
    train_days = df[df["date_key"] < BACKTEST_START]["date_key"].nunique()
    test_days  = df[(df["date_key"] >= BACKTEST_START) &
                    (df["date_key"] <= BACKTEST_END)]["date_key"].nunique()
    zero_pct = (df[TARGET_COL] == 0).mean() * 100
    print(f"  训练集: {train_days} 天 | 测试集: {test_days} 天")
    print(f"  零价格占比: {zero_pct:.1f}% (集中在10-15时丰水季，真实市场信号)")
    print(f"  特征数: {len(FEATURE_COLS)}")

    # 2. Walk-forward backtest
    print("\n[2/4] Walk-forward backtest...")
    results = walk_forward_backtest(df)

    # 3. Print summary
    print("\n[3/4] Results summary")
    print_summary(results)

    # 4. Save P4-DA predictions to PostgreSQL → Metabase
    print("\n[4/4] Saving P4-DA predictions to PostgreSQL for Metabase...")
    save_predictions_to_pg(results, model_name="P4_DA")

    # 5. Log to MLflow
    print("\n[5/5] Logging to MLflow...")
    try:
        log_to_mlflow(results)
        print(f"  View at: {MLFLOW_URI}")
    except Exception as e:
        print(f"  MLflow logging skipped: {e}")

    print("\nDone.")
