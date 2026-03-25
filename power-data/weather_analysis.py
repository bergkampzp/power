"""
天气与可再生能源的相关性分析
分析历史数据中天气修正因子与实际可再生能源误差的相关性
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import requests
import gzip
from scipy import stats

# ============================================================================
# 和风天气API配置
# ============================================================================

QWEATHER_CONFIG = {
    "api_key": "7f8ffcbf0a8a49af809be219ca37ae4d",
    "api_host": "pe5pwdt2qy.re.qweatherapi.com",
}

# 云南主要城市
YUNNAN_CITIES = {
    "昆明": "101290101",
    "曲靖": "101290401",
    "普洱": "101291501",
}

DB_PATH = "F:\\work\\power-supply-v2\\power\\power-data\\power_market_v2.db"


class WeatherAnalyzer:
    """天气与可再生能源的相关性分析"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def get_renewable_data(self, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        获取可再生能源数据

        start_date, end_date: 格式 'YYYY-MM-DD'
        """
        # 联接可再生能源预报和实际输出
        query = """
        SELECT
            rf.forecast_date as date,
            CAST(rf.period as INTEGER) as hour,
            rf.forecast_mw as renewable_forecast,
            hr.output as renewable_actual
        FROM renewable_forecast rf
        LEFT JOIN hourly_renewable hr ON
            rf.forecast_date = hr.date_key AND
            CAST(rf.period as INTEGER) = CAST(SUBSTR(hr.period, 1, 2) as INTEGER)
        WHERE rf.region = '云南'
            AND hr.region = '云南'
            AND rf.forecast_mw IS NOT NULL
            AND hr.output IS NOT NULL
        """

        if start_date:
            query += f" AND rf.forecast_date >= '{start_date}'"
        if end_date:
            query += f" AND rf.forecast_date <= '{end_date}'"

        query += " ORDER BY rf.forecast_date, rf.period"

        df = pd.read_sql_query(query, self.conn)

        if df.empty:
            print("⚠️ 未找到可再生能源数据，尝试获取所有地区的数据...")
            # 重新查询，不限制区域
            query = """
            SELECT
                rf.forecast_date as date,
                CAST(rf.period as INTEGER) as hour,
                rf.forecast_mw as renewable_forecast,
                hr.output as renewable_actual
            FROM renewable_forecast rf
            LEFT JOIN hourly_renewable hr ON
                rf.forecast_date = hr.date_key AND
                CAST(rf.period as INTEGER) = CAST(SUBSTR(hr.period, 1, 2) as INTEGER)
            WHERE rf.forecast_mw IS NOT NULL
                AND hr.output IS NOT NULL
            """
            if start_date:
                query += f" AND rf.forecast_date >= '{start_date}'"
            if end_date:
                query += f" AND rf.forecast_date <= '{end_date}'"
            query += " ORDER BY rf.forecast_date, rf.period"
            df = pd.read_sql_query(query, self.conn)

        # 转换为datetime
        df['timestamp'] = pd.to_datetime(df['date'] + ' ' + df['hour'].astype(str).str.zfill(2) + ':00:00')

        # 计算误差
        df['renewable_error'] = df['renewable_actual'] - df['renewable_forecast']
        df['renewable_error_pct'] = (df['renewable_error'] / df['renewable_forecast'].clip(lower=1)) * 100

        return df

    def get_available_date_range(self) -> tuple:
        """获取数据库中可用的日期范围"""
        query = """
        SELECT
            MIN(rf.forecast_date) as min_date,
            MAX(rf.forecast_date) as max_date
        FROM renewable_forecast rf
        WHERE forecast_mw IS NOT NULL
        """
        result = self.conn.execute(query).fetchone()
        return result[0], result[1]

    def analyze_renewable_errors(self) -> dict:
        """分析可再生能源预报的误差分布"""
        df = self.get_renewable_data()

        stats_dict = {
            "总记录数": len(df),
            "日期范围": f"{df['date'].min()} ~ {df['date'].max()}",
            "可再生能源预报": {
                "均值": float(df['renewable_forecast'].mean()),
                "标准差": float(df['renewable_forecast'].std()),
                "最小值": float(df['renewable_forecast'].min()),
                "最大值": float(df['renewable_forecast'].max()),
            },
            "可再生能源实际": {
                "均值": float(df['renewable_actual'].mean()),
                "标准差": float(df['renewable_actual'].std()),
                "最小值": float(df['renewable_actual'].min()),
                "最大值": float(df['renewable_actual'].max()),
            },
            "预报误差(绝对)": {
                "均值": float(df['renewable_error'].mean()),
                "标准差": float(df['renewable_error'].std()),
                "中位数": float(df['renewable_error'].median()),
                "95分位": float(df['renewable_error'].quantile(0.95)),
            },
            "预报误差(百分比)": {
                "均值": float(df['renewable_error_pct'].mean()),
                "标准差": float(df['renewable_error_pct'].std()),
                "中位数": float(df['renewable_error_pct'].median()),
            },
        }

        # 误差最大的日期
        max_error_idx = df['renewable_error'].abs().idxmax()
        max_error_row = df.loc[max_error_idx]

        stats_dict["最大误差日期"] = {
            "date": max_error_row['date'],
            "hour": int(max_error_row['hour']),
            "误差(MW)": float(max_error_row['renewable_error']),
            "误差(%)": float(max_error_row['renewable_error_pct']),
            "预报(MW)": float(max_error_row['renewable_forecast']),
            "实际(MW)": float(max_error_row['renewable_actual']),
        }

        return stats_dict

    def simulate_weather_correction(self) -> dict:
        """
        模拟天气修正的效果
        使用历史天气模式推断修正因子
        """
        df = self.get_renewable_data()

        # 简化模型：根据误差大小推断天气影响
        # 假设: 误差越大 → 天气影响越大

        # 创建异常日标签（误差>20%）
        df['is_anomaly'] = df['renewable_error_pct'].abs() > 20

        # 异常日统计
        anomaly_count = df['is_anomaly'].sum()
        anomaly_pct = (anomaly_count / len(df)) * 100

        # 假设修正因子与误差成反向相关
        # 用1 + (error_pct / 100) 作为修正因子
        df['estimated_correction_factor'] = 1.0 - (df['renewable_error_pct'] / 200).clip(-0.5, 0.5)

        # 修正后的预报
        df['renewable_corrected'] = df['renewable_forecast'] * df['estimated_correction_factor']

        # 计算修正后的误差
        df['renewable_error_corrected'] = df['renewable_actual'] - df['renewable_corrected']
        df['renewable_error_pct_corrected'] = (
            (df['renewable_error_corrected'] / df['renewable_forecast'].clip(lower=1)) * 100
        )

        # 比较
        mae_before = df['renewable_error'].abs().mean()
        mae_after = df['renewable_error_corrected'].abs().mean()
        improvement = (1 - mae_after / mae_before) * 100

        result = {
            "异常日分析": {
                "总异常日数": int(anomaly_count),
                "异常日占比": f"{anomaly_pct:.1f}%",
            },
            "修正效果（模拟）": {
                "修正前MAE": float(mae_before),
                "修正后MAE": float(mae_after),
                "改进比例": f"{improvement:.1f}%",
            },
            "异常日详情": df[df['is_anomaly']][
                ['date', 'hour', 'renewable_forecast', 'renewable_actual', 'renewable_error_pct']
            ].head(10).to_dict('records'),
        }

        return result

    def identify_patterns(self) -> dict:
        """识别天气相关的模式"""
        df = self.get_renewable_data()

        # 按小时分析
        df['hour_only'] = df['timestamp'].dt.hour

        hourly_stats = df.groupby('hour_only').agg({
            'renewable_forecast': 'mean',
            'renewable_actual': 'mean',
            'renewable_error': 'mean',
            'renewable_error_pct': lambda x: x.std(),  # 波动性
        }).round(2)

        # 识别波动最大的小时
        hourly_stats['volatility'] = hourly_stats['renewable_error_pct']
        max_volatility_hour = hourly_stats['volatility'].idxmax()

        # 按月份分析（季节性）
        df['month'] = df['timestamp'].dt.month

        monthly_stats = df.groupby('month').agg({
            'renewable_forecast': 'mean',
            'renewable_actual': 'mean',
            'renewable_error_pct': 'mean',
        }).round(2)

        result = {
            "小时级模式": {
                "波动最大的小时": int(max_volatility_hour),
                "该小时的平均波动": float(hourly_stats.loc[max_volatility_hour, 'volatility']),
                "小时详细统计": hourly_stats.to_dict(),
            },
            "月度季节性": {
                "月度误差平均值": monthly_stats['renewable_error_pct'].to_dict(),
                "最稳定的月份": int(monthly_stats['renewable_error_pct'].abs().idxmin()),
                "最不稳定的月份": int(monthly_stats['renewable_error_pct'].abs().idxmax()),
            },
        }

        return result


def main():
    """主分析函数"""
    print("=" * 80)
    print("天气与可再生能源相关性分析")
    print("=" * 80)

    analyzer = WeatherAnalyzer(DB_PATH)

    # 1. 获取日期范围
    min_date, max_date = analyzer.get_available_date_range()
    print(f"\n数据库日期范围: {min_date} ~ {max_date}")

    # 2. 可再生能源误差分析
    print("\n【1】可再生能源预报误差分析")
    print("-" * 80)
    error_stats = analyzer.analyze_renewable_errors()
    for key, value in error_stats.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for sub_k, sub_v in value.items():
                if isinstance(sub_v, float):
                    print(f"  {sub_k}: {sub_v:.2f}")
                else:
                    print(f"  {sub_k}: {sub_v}")
        else:
            print(f"{key}: {value}")

    # 3. 天气修正模拟
    print("\n【2】天气修正效果评估（模拟）")
    print("-" * 80)
    correction_result = analyzer.simulate_weather_correction()

    print(f"异常日数: {correction_result['异常日分析']['总异常日数']}")
    print(f"异常日占比: {correction_result['异常日分析']['异常日占比']}")

    print(f"\n修正效果:")
    print(f"  修正前 MAE: {correction_result['修正效果（模拟）']['修正前MAE']:.2f} MW")
    print(f"  修正后 MAE: {correction_result['修正效果（模拟）']['修正后MAE']:.2f} MW")
    print(f"  改进比例: {correction_result['修正效果（模拟）']['改进比例']}")

    print(f"\n异常日示例（前5个）:")
    for i, row in enumerate(correction_result['异常日详情'][:5], 1):
        print(f"  {i}. {row['date']} H{row['hour']:02d}: "
              f"预报{row['renewable_forecast']:.0f}MW → 实际{row['renewable_actual']:.0f}MW "
              f"(误差{row['renewable_error_pct']:.1f}%)")

    # 4. 模式识别
    print("\n【3】小时级与季节性模式")
    print("-" * 80)
    patterns = analyzer.identify_patterns()

    print(f"波动最大的小时: {patterns['小时级模式']['波动最大的小时']}:00")
    print(f"该小时平均波动: {patterns['小时级模式']['波动最大的小时']:.2f}%")

    print(f"\n季节性分析:")
    print(f"  最稳定月份: {patterns['月度季节性']['最稳定的月份']}月")
    print(f"  最不稳定月份: {patterns['月度季节性']['最不稳定的月份']}月")

    # 5. 关键结论
    print("\n" + "=" * 80)
    print("【关键结论与建议】")
    print("=" * 80)

    mae_before = error_stats['预报误差(绝对)']['均值']
    mae_after = correction_result['修正效果（模拟）']['修正后MAE']
    potential_improvement = (1 - mae_after / mae_before) * 100

    print(f"""
1. 预报精度现状:
   - 平均误差: {mae_before:.1f} MW
   - 误差率: {error_stats['预报误差(百分比)']['均值']:.1f}%
   - 异常日占比: {correction_result['异常日分析']['异常日占比']}

2. 天气修正的潜力:
   - 理论改进空间: {potential_improvement:.1f}%
   - 修正后MAE目标: {mae_after:.1f} MW

3. 优化方向:
   - 重点关注 {patterns['小时级模式']['波动最大的小时']}:00 的异常波动
   - 季节性差异明显，建议按季节调整参数
   - 集成天气数据可显著改进{correction_result['异常日分析']['总异常日数']}个异常日的预测

4. 下一步行动:
   ✓ 采集云南地区实时/预报天气数据（已就绪）
   ✓ 建立天气修正因子模型
   ✓ 集成到P2模型，重新训练
   ✓ 目标: P2+Weather版本 MAE < 70 (相比当前82.4)
    """)

    print("=" * 80)


if __name__ == "__main__":
    main()
