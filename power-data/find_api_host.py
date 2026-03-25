"""
找到正确的和风天气API Host
"""
import requests
import json
import gzip
import sys

sys.stdout.reconfigure(encoding='utf-8')

API_KEY = "7f8ffcbf0a8a49af809be219ca37ae4d"
CREDENTIAL_ID = "C7H25HGQCC"
LOCATION = "101290101"  # 昆明

# 尝试多个可能的host
possible_hosts = [
    "api.qweather.com",
    "api.qweather.service.com",
    f"{CREDENTIAL_ID}.qweatherapi.com",
    f"devapi.qweather.com",
    f"geoapi.qweather.com",
    "qweather.api.com",
]

print("尝试不同的API Host...")
print("=" * 60)

for host in possible_hosts:
    url = f"https://{host}/v7/weather/now"
    params = {
        "location": LOCATION,
        "key": API_KEY,
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers={"Accept-Encoding": "gzip"},
            timeout=5
        )

        status = response.status_code

        if status == 200:
            try:
                if response.headers.get('Content-Encoding') == 'gzip':
                    data = json.loads(gzip.decompress(response.content).decode('utf-8'))
                else:
                    data = response.json()
                print(f"✓ {host:40} -> 200 (SUCCESS)")
                print(f"  数据: {list(data.keys())}")
                print(f"  详细: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")
            except:
                print(f"? {host:40} -> {status} (但数据解析失败)")
        else:
            error_msg = response.text[:100] if response.text else "无错误信息"
            print(f"✗ {host:40} -> {status} ({error_msg})")

    except requests.exceptions.Timeout:
        print(f"✗ {host:40} -> 超时")
    except requests.exceptions.ConnectionError:
        print(f"✗ {host:40} -> 连接失败")
    except Exception as e:
        print(f"✗ {host:40} -> 错误: {type(e).__name__}")

print("\n" + "=" * 60)
print("如果以上都失败，请检查:")
print("1. 用户凭据是否有效")
print("2. API Key是否有使用限制(IP白名单、应用限制等)")
print("3. 从和风天气控制台查看正确的API Host")
