#!/usr/bin/env python3
"""
电力市场API下载器 - 日前电价
目标: 下载单日或多日的日前电价数据(96点/15分钟粒度)，仅云南省
"""
import json, sys
from datetime import datetime, timedelta
import urllib.request

COOKIE = "CAMSID=B4B9D828DE104B41CAFD30F1A53B4099"
API_URL = "https://spot.poweremarket.com/uptspot/ma/spot/spottrade/scptp/sr/mp/spottrade/tdSpotRecentlyResultUserInfo/getList"

def fetch_day_ahead_price(date_str):
    """获取指定日期的日前电价数据"""
    req = urllib.request.Request(API_URL, method="POST")
    req.add_header("Content-Type", "application/json;charset=UTF-8")
    req.add_header("Cookie", COOKIE)
    req.add_header("Origin", "https://spot.poweremarket.com")
    req.add_header("Referer", "https://spot.poweremarket.com/uptspot/sr/spot/portalweb/to/ResultsGenerationIndex.html")
    req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36")
    req.add_header("Accept", "application/json, text/plain, */*")
    req.add_header("Accept-Language", "zh-CN,zh;q=0.9")
    req.add_header("sec-ch-ua", '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"')
    req.add_header("sec-ch-ua-mobile", "?0")
    req.add_header("sec-ch-ua-platform", "Linux")
    
    body = json.dumps({"operatingDate": date_str}).encode("utf-8")
    
    try:
        with urllib.request.urlopen(req, data=body, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e), "date": date_str}
    
    # 提取电价数据
    records = data.get("data", {}).get("data", [])
    if not records:
        records = data.get("data", [])
    
    result = {"date": date_str, "records": len(records), "prices": []}
    
    for r in records:
        exchange = r.get("exchange", "")
        # 取第一个有电价数据的记录
        if exchange == "04" or exchange == "":  # 云南或默认
            price_str = r.get("userRecentlyPrice", "")
            if price_str:
                try:
                    prices = json.loads(price_str) if isinstance(price_str, str) else price_str
                    vals = list(prices.values())
                    result["prices"] = prices
                    result["avg_price"] = sum(vals) / len(vals) if vals else 0
                    result["min_price"] = min(vals) if vals else 0
                    result["max_price"] = max(vals) if vals else 0
                    result["price_count"] = len(vals)
                    result["exchange"] = exchange
                    result["operating_date"] = r.get("operatingDate", "")
                    break
                except:
                    continue
    
    return result

def test_single_day():
    """测试单日下载"""
    print("=" * 60)
    print("测试: 下载单日前电价")
    print("=" * 60)
    
    result = fetch_day_ahead_price("2026-05-06")
    
    if "error" in result:
        print(f"❌ 失败: {result['error']}")
        return False
    
    if result.get("prices"):
        print(f"✅ 成功! 日期={result['date']}")
        print(f"   时间段数: {result['price_count']}")
        print(f"   均价:     {result['avg_price']:.1f} ¥/MWh")
        print(f"   最高:     {result['max_price']:.1f} ¥/MWh")
        print(f"   最低:     {result['min_price']:.1f} ¥/MWh")
        if result.get("exchange"):
            exchange_names = {"01": "广东", "02": "广西", "03": "贵州", "04": "云南", "05": "海南"}
            print(f"   区域:     {exchange_names.get(result['exchange'], result['exchange'])}")
        return True
    else:
        print(f"❌ 无电价数据 (记录数={result['records']})")
        return False

def download_range(start_date, end_date):
    """下载日期范围的日前电价"""
    print(f"\n{'='*60}")
    print(f"下载日期范围: {start_date} ~ {end_date}")
    print(f"{'='*60}")
    
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    
    all_data = {}
    current = start
    success = 0
    fail = 0
    
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        result = fetch_day_ahead_price(date_str)
        
        if "error" in result:
            print(f"  ❌ {date_str}: {result['error']}")
            fail += 1
        elif result.get("prices"):
            print(f"  ✅ {date_str}: {result['price_count']}时段, "
                  f"均价={result['avg_price']:.1f}, "
                  f"[{result['min_price']:.0f}~{result['max_price']:.0f}]")
            all_data[date_str] = result
            success += 1
        else:
            print(f"  ⚠️ {date_str}: 无数据 (记录={result['records']})")
            fail += 1
        
        current += timedelta(days=1)
    
    print(f"\n总计: {success}成功 / {fail}失败 / {success+fail}总天数")
    return all_data

if __name__ == "__main__":
    if len(sys.argv) > 2:
        download_range(sys.argv[1], sys.argv[2])
    else:
        # 默认测试2天
        test_single_day()
        download_range("2026-05-06", "2026-05-07")
