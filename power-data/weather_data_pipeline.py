"""
天气数据采集 + 修正因子计算管道
- 集成和风天气API
- 计算可再生能源修正因子
- 与P2模型融合

使用说明:
1. 从和风天气控制台-设置中查看API Host
2. 修改下面的 QWEATHER_CONFIG
3. 运行脚本
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
import json
import gzip
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import sqlite3

# ============================================================================
# 配置区域 - 需要用户填入正确的API Host
# ============================================================================

QWEATHER_CONFIG = {
    "api_key": "7f8ffcbf0a8a49af809be219ca37ae4d",
    "credential_id": "C7H25HGQCC",
    "api_host": "pe5pwdt2qy.re.qweatherapi.com",  # ✓ 正确的开发者host
    "use_api_key_auth": True,  # True=API Key认证, False=JWT认证
}

# 云南主要城市（根据可再生能源分布）
YUNNAN_CITIES = {
    "昆明": {
        "location_id": "101290101",
        "region": "central",
        "note": "云南省会，负荷中心"
    },
    "怒江": {
        "location_id": "101291901",
        "region": "northwest",
        "note": "大型水电项目区"
    },
    "迪庆": {
        "location_id": "101292201",
        "region": "north",
        "note": "高海拔，风力资源"
    },
    "曲靖": {
        "location_id": "101290401",
        "region": "northeast",
        "note": "光伏集中区"
    },
    "普洱": {
        "location_id": "101291501",
        "region": "southeast",
        "note": "生物质资源"
    },
}

# ============================================================================
# 核心类
# ============================================================================

class QWeatherClient:
    """和风天气API客户端"""

    def __init__(self, config: Dict):
        self.api_key = config["api_key"]
        self.credential_id = config["credential_id"]
        self.api_host = config["api_host"]
        self.use_api_key_auth = config["use_api_key_auth"]

    def _request(self, endpoint: str, params: Dict) -> Dict:
        """发送API请求"""
        url = f"https://{self.api_host}{endpoint}"

        # 添加认证
        if self.use_api_key_auth:
            params["key"] = self.api_key
            headers = {"Accept-Encoding": "gzip"}
        else:
            # JWT认证（如果需要）
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept-Encoding": "gzip"
            }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                # 处理gzip压缩（更robust的方式）
                try:
                    if response.headers.get('Content-Encoding') == 'gzip':
                        data = json.loads(gzip.decompress(response.content).decode('utf-8'))
                    else:
                        data = response.json()
                except (OSError, gzip.BadGzipFile):
                    # 如果gzip解析失败，直接用json
                    data = response.json()
                return {"success": True, "data": data}
            else:
                return {"success": False, "error": response.text, "status": response.status_code}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_now_weather(self, location_id: str, lang: str = "zh") -> Dict:
        """获取实时天气"""
        return self._request("/v7/weather/now", {
            "location": location_id,
            "lang": lang,
        })

    def get_hourly_forecast(self, location_id: str, hours: int = 24, lang: str = "zh") -> Dict:
        """获取逐小时预报（24小时或168小时）"""
        endpoint = "/v7/weather/168h" if hours > 72 else "/v7/weather/24h"
        return self._request(endpoint, {
            "location": location_id,
            "lang": lang,
        })

    def get_daily_forecast(self, location_id: str, days: int = 7, lang: str = "zh") -> Dict:
        """获取日预报"""
        return self._request("/v7/weather/7d", {
            "location": location_id,
            "lang": lang,
        })


class WeatherCorrectionFactor:
    """天气修正因子计算器"""

    @staticmethod
    def solar_correction(
        cloud_cover: float,
        temperature: float,
        relative_humidity: float
    ) -> float:
        """
        光伏修正因子

        参数:
        - cloud_cover: 云覆盖率 (%)
        - temperature: 温度 (°C)
        - relative_humidity: 相对湿度 (%)

        返回:
        - 修正因子 (0.0 ~ 1.5, 1.0 = 无修正)
        """
        # 基础修正：云覆盖
        # 完全晴朗(0%) -> 1.0, 完全阴云(100%) -> 0.1
        cloud_factor = 1.0 - (cloud_cover / 100.0) * 0.9

        # 温度系数（硅面板随温度升高效率下降 ~-0.4%/°C）
        # 标准工作温度25°C
        std_temp = 25
        if temperature > std_temp:
            temp_factor = 1.0 - (temperature - std_temp) * 0.004
        else:
            temp_factor = 1.0 + (std_temp - temperature) * 0.002

        # 湿度系数（高湿度降低透射，但也可能影响云的光学厚度）
        humidity_factor = 1.0 - (relative_humidity - 50) / 100 * 0.1 if relative_humidity > 50 else 1.0

        # 综合修正
        correction = cloud_factor * temp_factor * humidity_factor
        return np.clip(correction, 0.0, 1.5)

    @staticmethod
    def wind_power_correction(wind_speed: float, base_speed: float = 10.0) -> float:
        """
        风力发电修正因子

        参数:
        - wind_speed: 风速 (m/s)
        - base_speed: 基准风速 (m/s, 默认10)

        返回:
        - 修正因子 (0.0 ~ 2.0)
        """
        # 风能与风速3次方成正比
        if wind_speed < 3:  # 启动风速
            return 0.0
        if wind_speed > 25:  # 切出风速
            return 0.0

        # 相对风速的3次方
        ratio = (wind_speed / base_speed) ** 3
        return np.clip(ratio, 0.0, 2.0)

    @staticmethod
    def visibility_correction(visibility: float) -> float:
        """
        能见度修正（用于推断云层光学厚度）

        参数:
        - visibility: 能见度 (km)

        返回:
        - 修正因子 (0.5 ~ 1.2)
        """
        # 能见度差意味着气溶胶多或云多
        # 能见度 > 10km -> 1.0, < 5km -> 0.5
        if visibility > 10:
            return 1.0
        elif visibility < 5:
            return 0.5
        else:
            return 0.5 + (visibility - 5) / 5 * 0.5


class WeatherDataPipeline:
    """完整天气数据管道"""

    def __init__(self, db_path: str, config: Dict):
        self.db_path = db_path
        self.client = QWeatherClient(config)
        self.correction = WeatherCorrectionFactor()

    def fetch_current_weather(self, city: str, location_data: Dict) -> Dict:
        """获取当前天气"""
        location_id = location_data["location_id"]
        result = self.client.get_now_weather(location_id)

        if result["success"]:
            now_data = result["data"]["now"]
            return {
                "city": city,
                "timestamp": datetime.now().isoformat(),
                "temperature": float(now_data.get("temp", 0)),
                "wind_speed": float(now_data.get("windSpeed", 0)),
                "wind_direction": int(now_data.get("windDir360", 0)),
                "cloud_cover": int(now_data.get("cloud", 0)),
                "relative_humidity": int(now_data.get("humidity", 0)),
                "visibility": int(now_data.get("vis", 10)),
                "pressure": int(now_data.get("pressure", 1000)),
                "feelsLike": float(now_data.get("feelsLike", 0)),
                "text": now_data.get("text", "未知"),
            }
        else:
            print(f"✗ 获取{city}天气失败: {result.get('error')}")
            return None

    def fetch_all_cities(self) -> pd.DataFrame:
        """获取所有城市当前天气"""
        data_list = []

        for city, location_data in YUNNAN_CITIES.items():
            weather = self.fetch_current_weather(city, location_data)
            if weather:
                data_list.append(weather)
                print(f"✓ {city}: {weather['temperature']}°C, 风速{weather['wind_speed']}m/s, 云覆{weather['cloud_cover']}%")

        df = pd.DataFrame(data_list)
        return df

    def calculate_correction_factors(self, weather_df: pd.DataFrame) -> pd.DataFrame:
        """计算修正因子"""
        weather_df['solar_correction'] = weather_df.apply(
            lambda r: self.correction.solar_correction(
                r['cloud_cover'],
                r['temperature'],
                r['relative_humidity']
            ),
            axis=1
        )

        weather_df['wind_correction'] = weather_df.apply(
            lambda r: self.correction.wind_power_correction(r['wind_speed']),
            axis=1
        )

        weather_df['visibility_correction'] = weather_df.apply(
            lambda r: self.correction.visibility_correction(r['visibility']),
            axis=1
        )

        # 综合可再生能源修正
        # 权重: 光伏60% + 风力30% + 能见度10%
        weather_df['renewable_correction'] = (
            weather_df['solar_correction'] * 0.6 +
            weather_df['wind_correction'] * 0.3 +
            weather_df['visibility_correction'] * 0.1
        )

        return weather_df

    def save_to_db(self, weather_df: pd.DataFrame):
        """保存到数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            # 创建表
            conn.execute("""
            CREATE TABLE IF NOT EXISTS weather_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                city TEXT,
                temperature REAL,
                wind_speed REAL,
                wind_direction INTEGER,
                cloud_cover INTEGER,
                relative_humidity INTEGER,
                visibility INTEGER,
                pressure INTEGER,
                solar_correction REAL,
                wind_correction REAL,
                visibility_correction REAL,
                renewable_correction REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            weather_df.to_sql('weather_data', conn, if_exists='append', index=False)
            conn.commit()
            conn.close()
            print(f"✓ 保存{len(weather_df)}条天气数据到数据库")
        except Exception as e:
            print(f"✗ 数据库保存失败: {e}")


def main():
    """主函数"""
    print("=" * 70)
    print("天气数据采集 + 修正因子计算管道")
    print("=" * 70)

    # 检查配置
    print(f"\n配置检查:")
    print(f"  API Host: {QWEATHER_CONFIG['api_host']}")
    print(f"  API Key: {QWEATHER_CONFIG['api_key'][:10]}......")
    print(f"  认证方式: {'API Key' if QWEATHER_CONFIG['use_api_key_auth'] else 'JWT'}")

    print("\n⚠️ 注意:")
    print("1. 如果API返回403错误，请从和风天气控制台-设置中查看正确的API Host")
    print("2. 检查API Key是否有IP白名单限制")
    print("3. 当前为演示模式，需要手动输入正确的host")

    # 初始化管道
    db_path = "F:\\work\\power-supply-v2\\power\\power-data\\power_market_v2.db"
    pipeline = WeatherDataPipeline(db_path, QWEATHER_CONFIG)

    # 尝试获取天气数据
    print("\n开始获取天气数据...")
    try:
        weather_df = pipeline.fetch_all_cities()

        if not weather_df.empty:
            print(f"\n✓ 成功获取{len(weather_df)}个城市的天气数据")

            # 计算修正因子
            print("\n计算修正因子...")
            weather_df = pipeline.calculate_correction_factors(weather_df)

            # 显示结果
            print("\n修正因子结果:")
            print(weather_df[['city', 'temperature', 'wind_speed', 'cloud_cover',
                             'solar_correction', 'wind_correction', 'renewable_correction']].to_string())

            # 保存到数据库
            # pipeline.save_to_db(weather_df)

        else:
            print("✗ 未获取到天气数据")

    except Exception as e:
        print(f"✗ 错误: {e}")

    print("\n" + "=" * 70)
    print("下一步:")
    print("1. 修改QWEATHER_CONFIG中的api_host为正确值")
    print("2. 设计天气数据与renewable_forecast的相关性分析")
    print("3. 构建修正模型: renewable_forecast_corrected = forecast × correction_factor")
    print("4. 集成到P2模型，重新训练")
    print("=" * 70)


if __name__ == "__main__":
    main()
