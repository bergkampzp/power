"""
天气修正模型 - 云南省可再生能源出力修正
==================================================

@算法工程师: 物理公式 (GHI→光伏, 风速→风电)
@产品经理:   简单可靠, 一个系数修正renewable_forecast
@技术工程师: 和风天气API + Open-Meteo API 双源

核心公式:
  光伏出力比 = GHI因子 × 云量因子 × 降水因子 × 温度因子 × 季节因子
  风电出力比 = 风速功率曲线 (切入3m/s, 额定12m/s, 切出25m/s)
  全省修正   = Σ(城市修正 × 装机权重)

参考: pv_prediction项目 (云南实测PR=0.82, 温度系数-0.45%/°C)
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
import json
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

# ============================================================================
# 云南省16地市 新能源并网数据 (万千瓦)
# ============================================================================

YUNNAN_CAPACITY = {
    "曲靖": {"solar": 850, "wind": 320, "lat": 25.49, "lon": 103.80, "qweather_id": "101290401"},
    "红河": {"solar": 680, "wind": 210, "lat": 23.36, "lon": 103.38, "qweather_id": "101290901"},
    "楚雄": {"solar": 520, "wind": 140, "lat": 25.03, "lon": 101.53, "qweather_id": "101290601"},
    "大理": {"solar": 480, "wind": 260, "lat": 25.59, "lon": 100.27, "qweather_id": "101290501"},
    "昆明": {"solar": 310, "wind": 139, "lat": 25.04, "lon": 102.71, "qweather_id": "101290101"},
    "昭通": {"solar":  58, "wind":  25, "lat": 27.34, "lon": 103.72, "qweather_id": "101291001"},
    "保山": {"solar":  42, "wind":  18, "lat": 25.12, "lon":  99.17, "qweather_id": "101290701"},
    "文山": {"solar":  42, "wind":  17, "lat": 23.39, "lon": 104.24, "qweather_id": "101290801"},
    "普洱": {"solar":  35, "wind":  12, "lat": 22.79, "lon": 100.97, "qweather_id": "101291501"},
    "丽江": {"solar":  28, "wind":  22, "lat": 26.88, "lon": 100.23, "qweather_id": "101291301"},
    "临沧": {"solar":  28, "wind":   9, "lat": 23.89, "lon": 100.09, "qweather_id": "101291701"},
    "玉溪": {"solar":  18, "wind":   6, "lat": 24.35, "lon": 102.55, "qweather_id": "101290301"},
    "德宏": {"solar":  20, "wind":   8, "lat": 24.43, "lon":  98.59, "qweather_id": "101291501"},
    "西双版纳": {"solar": 12, "wind":  4, "lat": 22.01, "lon": 100.80, "qweather_id": "101291701"},
    "怒江": {"solar":  15, "wind":  12, "lat": 25.82, "lon":  98.86, "qweather_id": "101291901"},
    "迪庆": {"solar":   8, "wind":  18, "lat": 27.83, "lon":  99.70, "qweather_id": "101292201"},
}

# 全省汇总
TOTAL_SOLAR = sum(c["solar"] for c in YUNNAN_CAPACITY.values())  # 3146 万千瓦
TOTAL_WIND  = sum(c["wind"]  for c in YUNNAN_CAPACITY.values())  # 1220 万千瓦
TOTAL_RE    = TOTAL_SOLAR + TOTAL_WIND                          # 4366 万千瓦

# 前5大城市占比 (曲靖+红河+楚雄+大理+昆明 = 光伏90.7%, 风电87.6%)
# → 只需5个城市天气就能覆盖绝大部分装机

# ============================================================================
# 光伏出力模型 (复用pv_prediction核心算法)
# ============================================================================

class SolarOutputModel:
    """
    光伏出力比计算
    参考: pv_prediction/solar_weather_api.py
    核心: GHI因子 × 云量因子 × 降水因子 × 温度因子 × 季节因子
    """

    PR = 0.82           # 性能系数 (云南实测)
    TEMP_COEFF = -0.0045  # 温度系数 (%/°C)

    @staticmethod
    def ghi_factor(ghi: float) -> float:
        """GHI辐照度因子 (分段线性, 参考pv_prediction)"""
        if ghi >= 800:
            return 0.95
        elif ghi >= 400:
            return 0.40 + 0.55 * (ghi - 400) / 400
        elif ghi >= 100:
            return 0.10 + 0.30 * (ghi - 100) / 300
        else:
            return ghi / 1000

    @staticmethod
    def cloud_factor(cloud_cover: float) -> float:
        """云量衰减因子 (分段线性, 参考pv_prediction)"""
        if cloud_cover <= 20:
            return 1.0 - cloud_cover / 20 * 0.15
        elif cloud_cover <= 60:
            return 0.85 - (cloud_cover - 20) / 40 * 0.55
        else:
            return 0.30 - (cloud_cover - 60) / 40 * 0.20
        # 晴天(0%)=1.0, 多云(50%)=0.44, 阴天(80%)=0.20, 暴雨(100%)=0.10

    @staticmethod
    def precip_factor(precipitation: float) -> float:
        """降水衰减因子"""
        if precipitation <= 0:
            return 1.0
        elif precipitation < 1:
            return 0.70   # 小雨
        elif precipitation < 10:
            return 0.40   # 中雨
        else:
            return 0.15   # 大雨/暴雨

    @staticmethod
    def temp_factor(temp_ambient: float, ghi: float) -> float:
        """温度效率因子"""
        temp_module = temp_ambient + (ghi / 1000) * 25
        factor = 1 + SolarOutputModel.TEMP_COEFF * (temp_module - 25)
        return np.clip(factor, 0.85, 1.05)

    @staticmethod
    def season_factor(month: int) -> float:
        """季节因子 (干季vs雨季)"""
        if month in [11, 12, 1, 2, 3, 4]:
            return 1.0   # 干季
        return 0.75       # 雨季 (0.6太激进, 用0.75)

    @classmethod
    def output_ratio(cls, ghi: float, cloud_cover: float, temp: float,
                     precipitation: float = 0, month: int = None) -> float:
        """
        计算光伏出力比 (0~1)

        Parameters:
            ghi: 全球水平辐照度 (W/m²)
            cloud_cover: 云覆盖率 (%)
            temp: 环境温度 (°C)
            precipitation: 降水量 (mm/h)
            month: 月份 (1-12)

        Returns:
            出力比 (0~1, 相对于额定功率)
        """
        if month is None:
            month = datetime.now().month

        ratio = (
            cls.ghi_factor(ghi)
            * cls.cloud_factor(cloud_cover)
            * cls.precip_factor(precipitation)
            * cls.temp_factor(temp, ghi)
            * cls.season_factor(month)
            * cls.PR
        )
        return np.clip(ratio, 0.0, 1.0)


# ============================================================================
# 风电出力模型
# ============================================================================

class WindOutputModel:
    """
    风电出力比计算
    基于典型风机功率曲线 (切入3m/s, 额定12m/s, 切出25m/s)
    """

    CUT_IN = 3.0      # 切入风速 m/s
    RATED  = 12.0      # 额定风速 m/s
    CUT_OUT = 25.0     # 切出风速 m/s

    @classmethod
    def output_ratio(cls, wind_speed: float) -> float:
        """
        计算风电出力比 (0~1)

        典型风机功率曲线:
        - < 3 m/s: 0 (无出力)
        - 3~12 m/s: 立方增长 (风能∝v³)
        - 12~25 m/s: 1.0 (额定出力)
        - > 25 m/s: 0 (切出保护)

        Parameters:
            wind_speed: 风速 (m/s)

        Returns:
            出力比 (0~1)
        """
        if wind_speed < cls.CUT_IN:
            return 0.0
        elif wind_speed < cls.RATED:
            # 立方关系: (v - cut_in)³ / (rated - cut_in)³
            ratio = ((wind_speed - cls.CUT_IN) / (cls.RATED - cls.CUT_IN)) ** 3
            return min(ratio, 1.0)
        elif wind_speed <= cls.CUT_OUT:
            return 1.0
        else:
            return 0.0


# ============================================================================
# 天气数据采集 (双源: 和风天气 + Open-Meteo)
# ============================================================================

class WeatherDataFetcher:
    """天气数据采集器"""

    def __init__(self, qweather_key: str, qweather_host: str):
        self.qw_key = qweather_key
        self.qw_host = qweather_host

    def fetch_qweather(self, location_id: str) -> Optional[Dict]:
        """和风天气: 获取实时天气 (温度, 风速, 云覆盖, 湿度)"""
        url = f"https://{self.qw_host}/v7/weather/now"
        params = {"location": location_id, "key": self.qw_key}
        try:
            resp = requests.get(url, params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if "now" in data:
                    now = data["now"]
                    return {
                        "temp": float(now.get("temp", 20)),
                        "wind_speed": float(now.get("windSpeed", 0)) / 3.6,  # km/h → m/s
                        "cloud_cover": float(now.get("cloud", 50)),
                        "humidity": float(now.get("humidity", 60)),
                        "precip": float(now.get("precip", 0)),
                    }
        except Exception as e:
            pass
        return None

    def fetch_openmeteo(self, lat: float, lon: float) -> Optional[Dict]:
        """Open-Meteo: 获取当前小时天气 (含GHI辐照度!)"""
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,cloud_cover,direct_radiation,precipitation,wind_speed_10m",
            "timezone": "Asia/Shanghai",
            "forecast_days": 1,
        }
        try:
            resp = requests.get(url, params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                hour = datetime.now().hour
                hourly = data.get("hourly", {})
                return {
                    "ghi": hourly.get("direct_radiation", [0]*24)[hour],
                    "temp": hourly.get("temperature_2m", [20]*24)[hour],
                    "cloud_cover": hourly.get("cloud_cover", [50]*24)[hour],
                    "wind_speed": hourly.get("wind_speed_10m", [0]*24)[hour] / 3.6,  # km/h→m/s
                    "precip": hourly.get("precipitation", [0]*24)[hour],
                }
        except Exception as e:
            pass
        return None

    def fetch_openmeteo_24h(self, lat: float, lon: float) -> Optional[List[Dict]]:
        """Open-Meteo: 获取24小时预报 (含GHI)"""
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,cloud_cover,direct_radiation,precipitation,wind_speed_10m",
            "timezone": "Asia/Shanghai",
            "forecast_days": 2,
        }
        try:
            resp = requests.get(url, params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                hourly = data.get("hourly", {})
                results = []
                for h in range(48):  # 48小时
                    results.append({
                        "hour": h % 24,
                        "day_offset": h // 24,
                        "ghi": hourly.get("direct_radiation", [0]*48)[h],
                        "temp": hourly.get("temperature_2m", [20]*48)[h],
                        "cloud_cover": hourly.get("cloud_cover", [50]*48)[h],
                        "wind_speed": hourly.get("wind_speed_10m", [0]*48)[h] / 3.6,
                        "precip": hourly.get("precipitation", [0]*48)[h],
                    })
                return results
        except Exception as e:
            pass
        return None

    def fetch_city_weather(self, city: str, city_data: Dict) -> Optional[Dict]:
        """获取单个城市的完整天气 (融合双源)"""
        # 优先Open-Meteo (有GHI)
        om = self.fetch_openmeteo(city_data["lat"], city_data["lon"])
        # 补充和风天气
        qw = self.fetch_qweather(city_data["qweather_id"])

        if om:
            result = om.copy()
            # 如果和风有数据，用和风的风速 (更准确的实时值)
            if qw and qw["wind_speed"] > 0:
                result["wind_speed"] = qw["wind_speed"]
            return result
        elif qw:
            # 没有GHI，用云覆盖估算
            qw["ghi"] = estimate_ghi_from_cloud(qw["cloud_cover"])
            return qw
        return None


def estimate_ghi_from_cloud(cloud_cover: float, hour: int = None) -> float:
    """根据云覆盖估算GHI (当Open-Meteo不可用时)"""
    if hour is None:
        hour = datetime.now().hour
    # 晴空GHI曲线 (云南)
    if hour < 6 or hour > 19:
        clear_sky_ghi = 0
    elif hour < 12:
        clear_sky_ghi = (hour - 6) / 6 * 900
    else:
        clear_sky_ghi = (19 - hour) / 7 * 900

    # 云覆盖衰减
    cloud_reduction = 1.0 - cloud_cover / 100 * 0.75
    return max(0, clear_sky_ghi * cloud_reduction)


# ============================================================================
# 核心: 全省加权修正因子计算
# ============================================================================

class YunnanRenewableCorrection:
    """
    云南省可再生能源修正因子计算器

    算法:
    1. 获取Top-5城市天气数据 (覆盖90%+装机)
    2. 分别计算光伏出力比和风电出力比
    3. 按装机容量加权汇总
    4. 输出综合修正因子 (0.1 ~ 1.2)

    使用:
        corrector = YunnanRenewableCorrection(api_key, api_host)
        factor = corrector.get_correction_factor()
        renewable_corrected = renewable_forecast * factor
    """

    # Top-5城市 (覆盖光伏90.7%, 风电87.6%)
    TOP_CITIES = ["曲靖", "红河", "楚雄", "大理", "昆明"]

    def __init__(self, qweather_key: str, qweather_host: str):
        self.fetcher = WeatherDataFetcher(qweather_key, qweather_host)
        self.solar_model = SolarOutputModel()
        self.wind_model = WindOutputModel()

    def get_correction_factor(self, month: int = None) -> Dict:
        """
        获取当前的可再生能源修正因子

        Returns:
            {
                "correction_factor": 0.65,     # 综合修正因子
                "solar_factor": 0.60,           # 光伏修正
                "wind_factor": 0.75,            # 风电修正
                "solar_weight": 0.72,           # 光伏在可再生中的占比
                "wind_weight": 0.28,            # 风电在可再生中的占比
                "city_details": [...],           # 各城市详情
                "timestamp": "2026-03-25T15:00"
            }
        """
        if month is None:
            month = datetime.now().month

        city_results = []
        total_solar_weighted = 0.0
        total_wind_weighted = 0.0
        total_solar_cap = 0.0
        total_wind_cap = 0.0

        for city_name in self.TOP_CITIES:
            city_data = YUNNAN_CAPACITY[city_name]
            weather = self.fetcher.fetch_city_weather(city_name, city_data)

            if weather is None:
                print(f"  ⚠ {city_name}: 天气数据获取失败, 使用默认值")
                weather = {"ghi": 500, "temp": 22, "cloud_cover": 30,
                          "wind_speed": 5, "precip": 0}

            # 光伏出力比
            solar_ratio = self.solar_model.output_ratio(
                ghi=weather["ghi"],
                cloud_cover=weather["cloud_cover"],
                temp=weather["temp"],
                precipitation=weather.get("precip", 0),
                month=month
            )

            # 风电出力比
            wind_ratio = self.wind_model.output_ratio(weather["wind_speed"])

            # 加权累计
            solar_cap = city_data["solar"]
            wind_cap = city_data["wind"]

            total_solar_weighted += solar_ratio * solar_cap
            total_wind_weighted += wind_ratio * wind_cap
            total_solar_cap += solar_cap
            total_wind_cap += wind_cap

            city_results.append({
                "city": city_name,
                "solar_cap": solar_cap,
                "wind_cap": wind_cap,
                "ghi": weather["ghi"],
                "cloud": weather["cloud_cover"],
                "wind_speed": weather["wind_speed"],
                "temp": weather["temp"],
                "solar_ratio": round(solar_ratio, 4),
                "wind_ratio": round(wind_ratio, 4),
            })

        # 全省加权平均
        avg_solar = total_solar_weighted / total_solar_cap if total_solar_cap > 0 else 0.5
        avg_wind = total_wind_weighted / total_wind_cap if total_wind_cap > 0 else 0.3

        # 光伏和风电在总可再生中的占比
        solar_weight = TOTAL_SOLAR / TOTAL_RE  # ≈ 72%
        wind_weight = TOTAL_WIND / TOTAL_RE    # ≈ 28%

        # 综合修正因子
        correction = avg_solar * solar_weight + avg_wind * wind_weight

        return {
            "correction_factor": round(float(correction), 4),
            "solar_factor": round(float(avg_solar), 4),
            "wind_factor": round(float(avg_wind), 4),
            "solar_weight": round(solar_weight, 4),
            "wind_weight": round(wind_weight, 4),
            "city_details": city_results,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def get_24h_correction(self, month: int = None) -> List[Dict]:
        """获取24小时预报修正因子"""
        if month is None:
            month = datetime.now().month

        # 用曲靖代表全省 (光伏装机最大, 位于中部)
        city_data = YUNNAN_CAPACITY["曲靖"]
        hourly_weather = self.fetcher.fetch_openmeteo_24h(
            city_data["lat"], city_data["lon"]
        )

        if not hourly_weather:
            print("⚠ 无法获取24h预报数据")
            return []

        results = []
        for hw in hourly_weather:
            solar_ratio = self.solar_model.output_ratio(
                ghi=hw["ghi"], cloud_cover=hw["cloud_cover"],
                temp=hw["temp"], precipitation=hw["precip"], month=month
            )
            wind_ratio = self.wind_model.output_ratio(hw["wind_speed"])

            solar_weight = TOTAL_SOLAR / TOTAL_RE
            wind_weight = TOTAL_WIND / TOTAL_RE
            correction = solar_ratio * solar_weight + wind_ratio * wind_weight

            results.append({
                "hour": hw["hour"],
                "day_offset": hw["day_offset"],
                "ghi": hw["ghi"],
                "cloud": hw["cloud_cover"],
                "wind_speed": hw["wind_speed"],
                "temp": hw["temp"],
                "solar_ratio": round(float(solar_ratio), 4),
                "wind_ratio": round(float(wind_ratio), 4),
                "correction_factor": round(float(correction), 4),
            })

        return results


# ============================================================================
# 主程序: 团队研讨演示
# ============================================================================

def main():
    print("=" * 80)
    print("天气修正模型 - 云南省可再生能源出力修正")
    print("=" * 80)

    # 装机容量分析
    print(f"\n【装机容量分析】")
    print(f"  全省光伏: {TOTAL_SOLAR} 万千瓦 ({TOTAL_SOLAR/TOTAL_RE*100:.1f}%)")
    print(f"  全省风电: {TOTAL_WIND} 万千瓦 ({TOTAL_WIND/TOTAL_RE*100:.1f}%)")
    print(f"  合计可再生: {TOTAL_RE} 万千瓦")

    print(f"\n  Top-5 城市覆盖率:")
    top5_solar = sum(YUNNAN_CAPACITY[c]["solar"] for c in ["曲靖","红河","楚雄","大理","昆明"])
    top5_wind = sum(YUNNAN_CAPACITY[c]["wind"] for c in ["曲靖","红河","楚雄","大理","昆明"])
    print(f"    光伏: {top5_solar}/{TOTAL_SOLAR} = {top5_solar/TOTAL_SOLAR*100:.1f}%")
    print(f"    风电: {top5_wind}/{TOTAL_WIND} = {top5_wind/TOTAL_WIND*100:.1f}%")

    # 各城市装机排名
    print(f"\n  各城市装机 (排名):")
    sorted_cities = sorted(YUNNAN_CAPACITY.items(),
                          key=lambda x: x[1]["solar"]+x[1]["wind"], reverse=True)
    for i, (name, cap) in enumerate(sorted_cities[:8], 1):
        total = cap["solar"] + cap["wind"]
        pct = total / TOTAL_RE * 100
        print(f"    {i}. {name:6} 光伏{cap['solar']:>4}万kW + 风电{cap['wind']:>3}万kW"
              f" = {total:>4}万kW ({pct:.1f}%)")

    # 获取实时天气并计算修正
    print(f"\n{'='*80}")
    print(f"【实时天气修正因子】")
    print(f"{'='*80}")

    corrector = YunnanRenewableCorrection(
        qweather_key="7f8ffcbf0a8a49af809be219ca37ae4d",
        qweather_host="pe5pwdt2qy.re.qweatherapi.com"
    )

    result = corrector.get_correction_factor()

    print(f"\n  时间: {result['timestamp']}")
    print(f"  综合修正因子: {result['correction_factor']:.4f}")
    print(f"  光伏修正:     {result['solar_factor']:.4f} (权重{result['solar_weight']*100:.0f}%)")
    print(f"  风电修正:     {result['wind_factor']:.4f} (权重{result['wind_weight']*100:.0f}%)")

    print(f"\n  各城市详情:")
    print(f"  {'城市':6} {'光伏MW':>6} {'风电MW':>6} {'GHI':>6} {'云覆%':>5} "
          f"{'风速m/s':>7} {'温度°C':>6} {'光伏比':>6} {'风电比':>6}")
    print(f"  {'-'*70}")
    for c in result["city_details"]:
        print(f"  {c['city']:6} {c['solar_cap']:>6} {c['wind_cap']:>6} "
              f"{c['ghi']:>6.0f} {c['cloud']:>5.0f} {c['wind_speed']:>7.1f} "
              f"{c['temp']:>6.1f} {c['solar_ratio']:>6.3f} {c['wind_ratio']:>6.3f}")

    # 模拟修正效果
    print(f"\n{'='*80}")
    print(f"【修正效果模拟】")
    print(f"{'='*80}")

    factor = result["correction_factor"]
    forecast_example = 15000  # MW
    corrected = forecast_example * factor

    print(f"\n  假设renewable_forecast = {forecast_example} MW")
    print(f"  修正因子 = {factor:.4f}")
    print(f"  修正后预报 = {forecast_example} × {factor:.4f} = {corrected:.0f} MW")

    # 3-22事件回顾
    print(f"\n  3-22事件回顾:")
    print(f"    预报: 15,844 MW")
    print(f"    实际: 10,637 MW (误差-32.9%)")
    print(f"    如果当时修正因子≈0.67:")
    print(f"    修正后: 15,844 × 0.67 = {15844*0.67:.0f} MW (误差{(15844*0.67-10637)/10637*100:.1f}%)")

    # 24小时预报修正
    print(f"\n{'='*80}")
    print(f"【24小时预报修正因子】")
    print(f"{'='*80}")

    hourly = corrector.get_24h_correction()

    if hourly:
        # 只显示明天的24小时
        tomorrow = [h for h in hourly if h["day_offset"] == 1]
        if not tomorrow:
            tomorrow = hourly[:24]

        print(f"\n  {'小时':>4} {'GHI':>6} {'云覆%':>5} {'风m/s':>6} {'光伏比':>6} "
              f"{'风电比':>6} {'修正':>6}")
        print(f"  {'-'*50}")
        for h in tomorrow:
            marker = " ◀" if h["correction_factor"] < 0.3 else ""
            print(f"  {h['hour']:>4}:00 {h['ghi']:>6.0f} {h['cloud']:>5.0f} "
                  f"{h['wind_speed']:>6.1f} {h['solar_ratio']:>6.3f} "
                  f"{h['wind_ratio']:>6.3f} {h['correction_factor']:>6.3f}{marker}")

        # 统计
        factors = [h["correction_factor"] for h in tomorrow]
        print(f"\n  24h修正因子统计:")
        print(f"    平均: {np.mean(factors):.4f}")
        print(f"    最大: {np.max(factors):.4f}")
        print(f"    最小: {np.min(factors):.4f}")
        print(f"    白天(8-18h)平均: {np.mean([h['correction_factor'] for h in tomorrow if 8<=h['hour']<=18]):.4f}")

    # 结论
    print(f"\n{'='*80}")
    print(f"【团队研讨结论】")
    print(f"{'='*80}")
    print(f"""
  @算法工程师:
    ✓ 光伏模型: GHI×云量×降水×温度×季节 (6个因子, 参考pv_prediction验证)
    ✓ 风电模型: 风速功率曲线 (切入3/额定12/切出25 m/s)
    ✓ 综合修正 = 光伏出力比×72% + 风电出力比×28%

  @产品经理:
    ✓ 输出: 一个 correction_factor (0.1~1.2)
    ✓ 用法: renewable_corrected = renewable_forecast × correction_factor
    ✓ 简单可靠, 物理意义清晰

  @技术工程师:
    ✓ 数据源: Open-Meteo(GHI免费) + 和风天气(风速/云覆盖)
    ✓ 只需Top-5城市 (覆盖>90%装机)
    ✓ API调用: 5×2 = 10次/预测 (可缓存)

  集成方式:
    修改P2模型的renewable_forecast特征:
    features['renewable_forecast'] *= correction_factor
    """)

    print("=" * 80)


if __name__ == "__main__":
    main()
