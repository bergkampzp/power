"""
和风天气API 探索脚本
获取云南地区天气数据，用于可再生能源预测修正
"""
import requests
import json
import gzip
from datetime import datetime, timedelta
import sys

# 和风天气API配置
API_KEY = "7f8ffcbf0a8a49af809be219ca37ae4d"
API_HOST = "api.qweather.com"  # 标准host，如果不对会从错误提示获取

# 云南主要城市/地区的Location ID
# 参考: https://dev.qweather.com/docs/api/geo/
YUNNAN_LOCATIONS = {
    "昆明": "101290101",      # Kunming
    "曲靖": "101290401",      # Qujing
    "保山": "101290701",      # Baoshan
    "丽江": "101291301",      # Lijiang
    "普洱": "101291501",      # Pu'er
    "临沧": "101291701",      # Lincang
    "怒江": "101291901",      # Nujiang (water/hydro rich)
    "迪庆": "101292201",      # Diqing (high altitude, wind potential)
}

def test_api_connection():
    """测试API连接"""
    print("=" * 60)
    print("和风天气API 连接测试")
    print("=" * 60)

    # 测试1: 获取实时天气
    url = f"https://{API_HOST}/v7/weather/now"
    params = {
        "location": YUNNAN_LOCATIONS["昆明"],
        "key": API_KEY,
        "lang": "zh"
    }

    try:
        print(f"\n测试URL: {url}")
        print(f"参数: {params}")

        response = requests.get(
            url,
            params=params,
            headers={"Accept-Encoding": "gzip"},
            timeout=10
        )

        print(f"状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")

        if response.status_code == 200:
            # 检查是否是gzip压缩
            if response.headers.get('Content-Encoding') == 'gzip':
                data = json.loads(gzip.decompress(response.content).decode('utf-8'))
            else:
                data = response.json()

            print(f"\n✓ API连接成功！")
            print(f"响应数据:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
            return True
        else:
            print(f"\n✗ API请求失败: {response.status_code}")
            print(f"响应: {response.text[:500]}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"\n✗ 网络错误: {e}")
        return False
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        return False

def explore_available_apis():
    """探索可用的API端点"""
    print("\n" + "=" * 60)
    print("可用的API端点探索")
    print("=" * 60)

    endpoints = {
        "实时天气": {
            "path": "/v7/weather/now",
            "params": {"location": YUNNAN_LOCATIONS["昆明"], "key": API_KEY},
            "description": "获取实时天气数据（温度、湿度、风速、云覆盖等）"
        },
        "7天预报": {
            "path": "/v7/weather/7d",
            "params": {"location": YUNNAN_LOCATIONS["昆明"], "key": API_KEY},
            "description": "获取7天天气预报"
        },
        "24小时预报": {
            "path": "/v7/weather/24h",
            "params": {"location": YUNNAN_LOCATIONS["昆明"], "key": API_KEY},
            "description": "获取24小时逐小时预报"
        },
        "实时空气质量": {
            "path": "/v4/air/now",
            "params": {"location": YUNNAN_LOCATIONS["昆明"], "key": API_KEY},
            "description": "获取实时空气质量（可用于能见度推断）"
        },
        "小时预报": {
            "path": "/v7/weather/168h",
            "params": {"location": YUNNAN_LOCATIONS["昆明"], "key": API_KEY},
            "description": "获取168小时（7天）逐小时预报"
        },
    }

    for name, info in endpoints.items():
        print(f"\n{name}:")
        print(f"  路径: {info['path']}")
        print(f"  说明: {info['description']}")

        url = f"https://{API_HOST}{info['path']}"
        try:
            response = requests.get(
                url,
                params=info['params'],
                headers={"Accept-Encoding": "gzip"},
                timeout=10
            )

            if response.status_code == 200:
                if response.headers.get('Content-Encoding') == 'gzip':
                    data = json.loads(gzip.decompress(response.content).decode('utf-8'))
                else:
                    data = response.json()

                print(f"  ✓ 可用 (返回keys: {list(data.keys())})")

                # 详细输出某些字段示例
                if 'now' in data:
                    print(f"  数据示例: temp={data['now'].get('temp')}, wind_speed={data['now'].get('windSpeed')}, cloud={data['now'].get('cloud')}")
                elif 'hourly' in data and len(data['hourly']) > 0:
                    sample = data['hourly'][0]
                    print(f"  数据示例: {sample}")

            else:
                print(f"  ✗ 状态码: {response.status_code}")

        except Exception as e:
            print(f"  ✗ 错误: {e}")

def get_location_ids():
    """获取云南所有可用的Location ID"""
    print("\n" + "=" * 60)
    print("云南地区 Location ID 列表")
    print("=" * 60)

    for city, loc_id in YUNNAN_LOCATIONS.items():
        print(f"{city:10} -> {loc_id}")

    return YUNNAN_LOCATIONS

def check_historical_data():
    """检查是否支持历史数据"""
    print("\n" + "=" * 60)
    print("历史数据可用性检查")
    print("=" * 60)

    # 尝试获取过去1天的数据
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    url = f"https://{API_HOST}/v7/weather/archive"
    params = {
        "location": YUNNAN_LOCATIONS["昆明"],
        "key": API_KEY,
        "date": yesterday,
        "lang": "zh"
    }

    print(f"\n尝试获取历史数据 (日期: {yesterday})")

    try:
        response = requests.get(
            url,
            params=params,
            headers={"Accept-Encoding": "gzip"},
            timeout=10
        )

        if response.status_code == 200:
            if response.headers.get('Content-Encoding') == 'gzip':
                data = json.loads(gzip.decompress(response.content).decode('utf-8'))
            else:
                data = response.json()

            print(f"✓ 支持历史数据接口")
            print(f"  返回keys: {list(data.keys())}")
            if 'daily' in data:
                print(f"  日数据: {data['daily']}")

        elif response.status_code == 404:
            print(f"✗ 历史数据接口不可用 (404)")
        else:
            print(f"✗ 状态码: {response.status_code}")

    except Exception as e:
        print(f"✗ 错误: {e}")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')

    # 运行所有探索
    success = test_api_connection()

    if success:
        explore_available_apis()
        get_location_ids()
        check_historical_data()

        print("\n" + "=" * 60)
        print("下一步: 设计数据采集和修正因子计算")
        print("=" * 60)
        print("""
1. 关键需求:
   - 云南地区实时+预报天气数据
   - 特别关注: 温度、风速、云覆盖率、相对湿度
   - 时间粒度: 小时级(与电力市场96period对齐)

2. 修正因子设计:
   - 光伏修正: cloud_cover + irradiance_factor
   - 风力修正: wind_speed correlation
   - 温度影响: panel_efficiency_coefficient

3. 数据融合:
   - 与renewable_forecast进行差值分析
   - 训练修正模型
   - 集成到P2模型

4. 性能指标:
   - 修正前: MAE=82.4
   - 目标: MAE<70 (同时3-22类异常+5%)
        """)
    else:
        print("\n✗ API连接失败，请检查:")
        print("  1. API KEY是否正确")
        print("  2. Host地址是否正确")
        print("  3. 网络连接是否正常")
