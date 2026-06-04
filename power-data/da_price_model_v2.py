"""
DA Price Prediction Model V2 — Two-Stage Market Clearing
=========================================================
Target  : 漫湾厂.500kV 次日日前节点电价 (24h)
Method  : Stage 1 零价格分类 + Stage 2 非零价格回归
Source  : PostgreSQL feat_da_features (dbt)

Stage 1: Zero-Price Classifier
  - Binary: will this hour's DA price be zero?
  - Key drivers: green_supply_ratio, is_solar_peak, seasonal_prior,
    prev_day_zero_count, residual_load_fc
  - Algorithm: LightGBM Classifier

Stage 2: Non-Zero Price Regressor (trained on price>0 only)
  - Ensemble: GBR(30%) + LightGBM(40%) + XGBoost(30%)
  - Key drivers: residual_load_fc, da_lag_1d, seasonal_prior,
    reserve_ratio, gap_lag_1d
  - Time-decay + season sample weighting

Final: price = (1 - P_zero) × Stage2_pred
       If P_zero > 0.7: price = 0
"""

import os
import sys
import warnings
import numpy as np
import psycopg2
from datetime import datetime

warnings.filterwarnings("ignore")

# Lazy-import pandas to handle numpy version issues
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
from sklearn.metrics import (mean_absolute_error, mean_squared_error, r2_score,
                             accuracy_score, f1_score, precision_score, recall_score)
import lightgbm as lgb
import xgboost as xgb

PG_CONN = dict(host="localhost", port=5433, user="postgres",
               password="postgres", dbname="warehouse")
BACKTEST_START = "20260301"
BACKTEST_END   = "20260322"

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 features: what predicts zero price
# These are the supply-demand fundamental features, NOT price lags.
# ─────────────────────────────────────────────────────────────────────────────
STAGE1_FEATURES = [
    # Supply-demand fundamentals (the REAL drivers)
    "residual_load_fc",       # key: negative = oversupply = zero risk
    "green_supply_ratio",     # key: >1 = green oversupply
    "renew_fc",               # absolute renewable forecast
    "load_fc",                # absolute load forecast
    "hydro_fc_avg",           # hydro available
    "reserve_load_ratio",     # reserve tightness
    # Time/season context
    "hour_feat",
    "is_solar_peak",          # 10-15h flag
    "is_evening_peak",        # 18-21h flag
    "is_wet_season",
    "month",
    "hour_sin", "hour_cos",
    "month_sin", "month_cos",
    # Historical zero patterns
    "zero_yesterday",         # was this hour zero yesterday?
    "prev_day_zero_count",    # total zeros in D-1
    "zero_band_ratio",        # zero ratio in nearby hours D-1
    # Lagged supply-demand
    "gap_lag_1d",
    "renew_lag_1d",
    "hydro_lag_1d",
    "renew_fc_share",
]

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 features: what determines price level (when price > 0)
# Mix of fundamentals + autocorrelation (both matter for non-zero regime)
# ─────────────────────────────────────────────────────────────────────────────
STAGE2_FEATURES = [
    # Market clearing fundamentals
    "residual_load_fc",
    "green_supply_ratio",
    "seasonal_prior",         # prior expectation from historical pattern
    "reserve_ratio",
    "reserve_load_ratio",
    "renew_fc",
    "load_fc",
    "hydro_fc_avg",
    "gen_fc",
    "flow_to_cap",            # congestion
    # DA price autocorrelation (still useful for non-zero)
    "da_lag_1d",
    "da_lag_2d",
    "da_lag_7d",
    "da_ma_3d",
    "da_ma_7d",
    "da_std_3d",
    "da_momentum_1d",
    "da_grid_lag_1d",
    # RT reference
    "rt_lag_1d",
    "rt_da_spread_lag1",
    # Supply-demand lags
    "load_lag_1d",
    "renew_lag_1d",
    "hydro_lag_1d",
    "gap_lag_1d",
    "renew_fc_vs_lag",
    # Grid operations
    "n_sections",
    "avg_limit",
    "maint_lag1d",
    "reserve_up_lag1d",
    "chan_lag1d",
    # Time
    "hour_feat",
    "dayofweek",
    "month",
    "is_weekend",
    "is_wet_season",
    "hour_sin", "hour_cos",
    "is_solar_peak",
    "is_evening_peak",
    "is_morning_peak",
    # Prev-day
    "prevday_da_avg",
    "prevday_da_max",
    "prevday_da_min",
    "prevday_da_std",
    "prevday_price_range",
    "da_vs_ma7_ratio",
]

TARGET_COL = "target_da_price"


def load_features() -> pd.DataFrame:
    conn = psycopg2.connect(**PG_CONN)
    all_cols = list(set(STAGE1_FEATURES + STAGE2_FEATURES + [TARGET_COL, "date_key", "hour"]))
    df = pd.read_sql(f"""
        SELECT {", ".join(all_cols)}
        FROM feat_da_features
        WHERE date_key >= '20250601'
        ORDER BY date_key, hour
    """, conn)
    conn.close()
    df = df.fillna(0)
    print(f"  Loaded {len(df)} rows, {df['date_key'].nunique()} days")
    print(f"  Stage 1 features: {len(STAGE1_FEATURES)}")
    print(f"  Stage 2 features: {len(STAGE2_FEATURES)}")
    return df


def compute_weights(train_df: pd.DataFrame, pred_date: str) -> np.ndarray:
    pred_dt = datetime.strptime(pred_date, "%Y%m%d")
    days_ago = train_df["date_key"].apply(
        lambda d: (pred_dt - datetime.strptime(d, "%Y%m%d")).days
    )
    time_w = np.exp(-np.log(2) * days_ago / 60)
    pred_month = pred_dt.month
    is_wet = (5 <= pred_month <= 10)
    train_wet = train_df["is_wet_season"].values.astype(bool)
    season_w = np.where(train_wet == is_wet, 2.0, 0.5)
    w = time_w * season_w
    return w / w.sum() * len(w)


def walk_forward_backtest(df: pd.DataFrame) -> pd.DataFrame:
    test_days = sorted([
        d for d in df["date_key"].unique()
        if BACKTEST_START <= d <= BACKTEST_END
    ])
    results = []
    all_hourly = []

    for test_date in test_days:
        train_df = df[df["date_key"] < test_date].copy()
        test_df  = df[df["date_key"] == test_date].copy()

        if len(train_df) < 500 or len(test_df) == 0:
            continue

        # ──────────────────────────────────────────────────────────────
        # Stage 1: Zero-Price Classifier
        # ──────────────────────────────────────────────────────────────
        y_cls = (train_df[TARGET_COL] == 0).astype(int).values
        X_cls = train_df[STAGE1_FEATURES].values

        clf = lgb.LGBMClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.85, is_unbalance=True,  # handle class imbalance
            verbose=-1, random_state=42
        )
        weights = compute_weights(train_df, test_date)
        clf.fit(X_cls, y_cls, sample_weight=weights)

        X_cls_test = test_df[STAGE1_FEATURES].values
        p_zero = clf.predict_proba(X_cls_test)[:, 1]  # P(zero)
        zero_pred = (p_zero > 0.5).astype(int)

        # Stage 1 metrics
        y_cls_test = (test_df[TARGET_COL] == 0).astype(int).values
        zero_acc = accuracy_score(y_cls_test, zero_pred)
        zero_f1  = f1_score(y_cls_test, zero_pred, zero_division=0)

        # ──────────────────────────────────────────────────────────────
        # Stage 2: Non-Zero Price Regressor (train on price > 0 only)
        # ──────────────────────────────────────────────────────────────
        nonzero_mask = train_df[TARGET_COL] > 0
        X_reg = train_df.loc[nonzero_mask, STAGE2_FEATURES].values
        y_reg = train_df.loc[nonzero_mask, TARGET_COL].values
        weights_reg = compute_weights(train_df[nonzero_mask], test_date)

        # Ensemble: GBR + LightGBM + XGBoost
        gbr = GradientBoostingRegressor(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.85, min_samples_leaf=3, random_state=42
        )
        lgbm = lgb.LGBMRegressor(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.85, verbose=-1, random_state=42
        )
        xgbm = xgb.XGBRegressor(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.85, verbosity=0, random_state=42
        )
        gbr.fit(X_reg, y_reg, sample_weight=weights_reg)
        lgbm.fit(X_reg, y_reg, sample_weight=weights_reg)
        xgbm.fit(X_reg, y_reg, sample_weight=weights_reg)

        X_reg_test = test_df[STAGE2_FEATURES].values
        stage2_pred = (
            0.30 * gbr.predict(X_reg_test) +
            0.40 * lgbm.predict(X_reg_test) +
            0.30 * xgbm.predict(X_reg_test)
        )

        # ──────────────────────────────────────────────────────────────
        # Combine: Final prediction
        # ──────────────────────────────────────────────────────────────
        # Soft combination: price = (1 - p_zero) * stage2_pred
        # Hard cutoff: if p_zero > 0.7, force to 0
        v2_pred = np.where(
            p_zero > 0.7,
            0.0,
            (1.0 - p_zero) * stage2_pred
        )
        v2_pred = np.clip(v2_pred, 0, None)  # no negative prices

        y_test = test_df[TARGET_COL].values
        hours  = test_df["hour"].values

        # ──────────────────────────────────────────────────────────────
        # Metrics by price regime
        # ──────────────────────────────────────────────────────────────
        overall_mae  = mean_absolute_error(y_test, v2_pred)
        overall_rmse = np.sqrt(mean_squared_error(y_test, v2_pred))
        overall_r2   = r2_score(y_test, v2_pred) if len(y_test) > 1 else 0

        # Non-zero only
        nz = y_test > 0
        if nz.sum() > 0:
            nz_mae = mean_absolute_error(y_test[nz], v2_pred[nz])
        else:
            nz_mae = 0

        # Zero-price accuracy
        zero_actual  = (y_test == 0).sum()
        zero_correct = ((v2_pred == 0) & (y_test == 0)).sum()

        print(f"  {test_date}: MAE={overall_mae:6.1f}  nz_MAE={nz_mae:6.1f}  "
              f"R²={overall_r2:6.3f}  "
              f"zero_acc={zero_acc:.2f} f1={zero_f1:.2f}  "
              f"zeros={zero_actual}/24 caught={zero_correct}")

        results.append({
            "date": test_date,
            "mae": round(overall_mae, 2),
            "nz_mae": round(nz_mae, 2),
            "rmse": round(overall_rmse, 2),
            "r2": round(overall_r2, 4),
            "zero_acc": round(zero_acc, 3),
            "zero_f1": round(zero_f1, 3),
            "zero_actual": int(zero_actual),
            "zero_caught": int(zero_correct),
            "n_hours": len(y_test),
        })

        for h, pred, actual, pz in zip(hours, v2_pred, y_test, p_zero):
            all_hourly.append({
                "date_key": test_date,
                "hour": int(h),
                "actual_price": float(actual),
                "predicted_price": float(pred),
                "p_zero": float(pz),
                "error": float(pred - actual),
                "abs_error": float(abs(pred - actual)),
            })

    return pd.DataFrame(results), pd.DataFrame(all_hourly)


def save_to_pg(hourly_df: pd.DataFrame):
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()

    cur.execute("""
        ALTER TABLE dashboard_predictions
        ADD COLUMN IF NOT EXISTS prediction_type VARCHAR(20) DEFAULT 'da_price',
        ADD COLUMN IF NOT EXISTS model_version VARCHAR(20);
    """)

    # Drop PK constraint if it blocks multi-version storage, recreate wider PK
    try:
        cur.execute("ALTER TABLE dashboard_predictions DROP CONSTRAINT IF EXISTS dashboard_predictions_pkey")
        cur.execute("""
            ALTER TABLE dashboard_predictions
            ADD CONSTRAINT dashboard_predictions_pkey
            PRIMARY KEY (date_key, hour, model_version)
        """)
    except Exception:
        conn.rollback()
    # Clear old V2 predictions
    cur.execute("DELETE FROM dashboard_predictions WHERE model_version = 'P4_DA_V2'")

    inserted = 0
    for _, r in hourly_df.iterrows():
        actual = r["actual_price"]
        cur.execute("""
            INSERT INTO dashboard_predictions
              (date_key, hour, actual_price, predicted_price, error, abs_error, pct_error,
               prediction_type, model_version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            r["date_key"], r["hour"], actual, r["predicted_price"],
            r["error"], r["abs_error"],
            float(abs(r["error"]) / actual * 100) if actual > 0 else 0,
            "da_price", "P4_DA_V2"
        ))
        inserted += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"  Saved {inserted} rows (model_version=P4_DA_V2)")


def log_mlflow(results_df: pd.DataFrame):
    try:
        import mlflow
        mlflow.set_tracking_uri("http://localhost:5002")
        mlflow.set_experiment("DA_Price_Prediction")

        avg_mae  = results_df["mae"].mean()
        avg_nz   = results_df["nz_mae"].mean()
        avg_r2   = results_df["r2"].mean()
        avg_zacc = results_df["zero_acc"].mean()
        avg_zf1  = results_df["zero_f1"].mean()

        with mlflow.start_run(run_name=f"V2_TwoStage_{datetime.now().strftime('%m%d_%H%M')}"):
            mlflow.log_param("model", "TwoStage_V2")
            mlflow.log_param("stage1", "LGBMClassifier_zero")
            mlflow.log_param("stage2", "GBR+LGBM+XGB_ensemble")
            mlflow.log_param("n_stage1_features", len(STAGE1_FEATURES))
            mlflow.log_param("n_stage2_features", len(STAGE2_FEATURES))
            mlflow.log_param("backtest_start", BACKTEST_START)
            mlflow.log_param("backtest_end", BACKTEST_END)

            mlflow.log_metric("avg_mae", round(avg_mae, 2))
            mlflow.log_metric("avg_nz_mae", round(avg_nz, 2))
            mlflow.log_metric("avg_r2", round(avg_r2, 4))
            mlflow.log_metric("avg_zero_acc", round(avg_zacc, 4))
            mlflow.log_metric("avg_zero_f1", round(avg_zf1, 4))

            for _, row in results_df.iterrows():
                step = int(row["date"][-2:])
                mlflow.log_metric("daily_mae", row["mae"], step=step)
                mlflow.log_metric("daily_r2", row["r2"], step=step)

        print(f"  MLflow: MAE={avg_mae:.2f} nz_MAE={avg_nz:.2f} R²={avg_r2:.4f} "
              f"zero_acc={avg_zacc:.3f} zero_f1={avg_zf1:.3f}")
    except Exception as e:
        print(f"  MLflow skipped: {e}")


def compare_v1_v2(v2_results: pd.DataFrame):
    """Load V1 results from PostgreSQL and compare"""
    conn = psycopg2.connect(**PG_CONN)
    v1 = pd.read_sql("""
        SELECT date_key,
               ROUND(AVG(abs_error)::numeric, 2) as mae,
               ROUND(AVG(CASE WHEN actual_price > 0 THEN abs_error END)::numeric, 2) as nz_mae,
               COUNT(*) as n
        FROM dashboard_predictions
        WHERE model_version = 'P4_DA' AND predicted_price > 0
        GROUP BY date_key ORDER BY date_key
    """, conn)
    conn.close()

    print("\n" + "="*85)
    print("V1 (单阶段GBR) vs V2 (两阶段市场出清) 逐日对比")
    print("="*85)
    print(f"{'日期':<12} {'V1 MAE':>8} {'V2 MAE':>8} {'改善':>8} "
          f"{'V1 nzMAE':>9} {'V2 nzMAE':>9} {'零价格':>8} {'V2判对':>8}")
    print("-"*85)

    total_v1, total_v2 = 0, 0
    wins_v2 = 0

    for _, v2r in v2_results.iterrows():
        v1_row = v1[v1["date_key"] == v2r["date"]]
        v1_mae = float(v1_row["mae"].iloc[0]) if len(v1_row) > 0 else 0
        v1_nz  = float(v1_row["nz_mae"].iloc[0]) if len(v1_row) > 0 else 0
        v2_mae = v2r["mae"]
        v2_nz  = v2r["nz_mae"]
        improve = v1_mae - v2_mae
        pct = (improve / v1_mae * 100) if v1_mae > 0 else 0
        marker = "✅" if improve > 0 else "❌"
        if improve > 0: wins_v2 += 1
        total_v1 += v1_mae
        total_v2 += v2_mae

        print(f"  {v2r['date']:<10} {v1_mae:>8.1f} {v2_mae:>8.1f} "
              f"{improve:>+7.1f}{marker} "
              f"{v1_nz:>9.1f} {v2_nz:>9.1f} "
              f"{v2r['zero_actual']:>5}/24 "
              f"{v2r['zero_caught']:>5}")

    n = len(v2_results)
    avg_v1 = total_v1 / n if n > 0 else 0
    avg_v2 = total_v2 / n if n > 0 else 0
    print("-"*85)
    print(f"  {'平均':<10} {avg_v1:>8.1f} {avg_v2:>8.1f} "
          f"{avg_v1-avg_v2:>+7.1f}{'✅' if avg_v2<avg_v1 else '❌'} "
          f"V2胜出: {wins_v2}/{n} 天")
    print("="*85)


def print_summary(results_df: pd.DataFrame):
    print("\n" + "="*70)
    print("DA PRICE V2 TWO-STAGE BACKTEST  (2026-03)")
    print("="*70)

    avg_mae  = results_df["mae"].mean()
    avg_nz   = results_df["nz_mae"].mean()
    avg_r2   = results_df["r2"].mean()
    avg_zacc = results_df["zero_acc"].mean()

    print(f"\n  总体 MAE:        {avg_mae:.2f} 元/MWh")
    print(f"  非零价格 MAE:    {avg_nz:.2f} 元/MWh")
    print(f"  总体 R²:         {avg_r2:.4f}")
    print(f"  零价格分类准确率: {avg_zacc:.1%}")
    print(f"  MAE最低日: {results_df.loc[results_df['mae'].idxmin(), 'date']} "
          f"({results_df['mae'].min():.1f})")
    print(f"  MAE最高日: {results_df.loc[results_df['mae'].idxmax(), 'date']} "
          f"({results_df['mae'].max():.1f})")

    # Grade distribution
    excellent = (results_df["mae"] < 30).sum()
    good      = ((results_df["mae"] >= 30) & (results_df["mae"] < 60)).sum()
    fair      = ((results_df["mae"] >= 60) & (results_df["mae"] < 100)).sum()
    poor      = (results_df["mae"] >= 100).sum()
    print(f"\n  精度分布: 优秀(<30): {excellent}天 | 良好(30-60): {good}天 | "
          f"一般(60-100): {fair}天 | 较差(>100): {poor}天")
    print("="*70)


if __name__ == "__main__":
    print("="*70)
    print(f"DA Price Model V2 — Two-Stage Market Clearing")
    print(f"  Stage 1: Zero-Price Classifier (LGBMClassifier)")
    print(f"  Stage 2: Non-Zero Regressor (GBR+LGBM+XGB)")
    print(f"  Backtest: {BACKTEST_START} → {BACKTEST_END}")
    print("="*70)

    # 1. Load
    print("\n[1/5] Loading features from dbt/PostgreSQL...")
    df = load_features()

    zero_total = (df[TARGET_COL] == 0).sum()
    zero_pct   = zero_total / len(df) * 100
    print(f"  零价格样本: {zero_total} ({zero_pct:.1f}%)")

    # 2. Backtest
    print("\n[2/5] Walk-forward backtest (two-stage)...")
    results, hourly = walk_forward_backtest(df)

    # 3. Summary
    print("\n[3/5] Summary")
    print_summary(results)

    # 4. Save to PostgreSQL
    print("\n[4/5] Saving V2 predictions to PostgreSQL...")
    save_to_pg(hourly)

    # 5. Compare V1 vs V2
    print("\n[5/5] V1 vs V2 comparison")
    compare_v1_v2(results)

    # 6. MLflow
    print("\n[6/6] MLflow logging...")
    log_mlflow(results)

    print("\nDone.")
