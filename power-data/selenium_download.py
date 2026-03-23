#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电力市场数据自动下载工具 - Selenium方案
使用Selenium模拟浏览器操作，自动选择日期并下载数据
"""

import os
import time
import subprocess
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# 配置
DOWNLOAD_DIR = os.path.expanduser("~/Downloads/电力数据")
START_DATE = "2026-01-12"
END_DATE = "2026-02-01"
WAIT_LOAD = 10  # 等待数据加载秒数
WAIT_CLICK = 3  # 点击间隔秒数

def setup_driver():
    """设置Chrome驱动"""
    chrome_options = Options()
    
    # Windows Chrome路径
    chrome_options.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    # 添加下载路径
    prefs = {
        "download.default_directory": DOWNLOAD_DIR.replace("/", "\\"),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    # 使用webdriver-manager自动下载
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.implicitly_wait(10)
    return driver

def select_date(driver, target_date):
    """选择日期 - 点击日历"""
    try:
        # 点击日期输入框打开日历
        date_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="选择日期"]')
        date_input.click()
        time.sleep(1)
        
        # 解析目标日期
        day = int(target_date.split("-")[2])
        
        # 找到所有可点击的日期单元格
        cells = driver.find_elements(By.CSS_SELECTOR, ".el-date-table td span:not(.disabled)")
        
        for cell in cells:
            try:
                day_text = cell.text
                if day_text == str(day):
                    cell.click()
                    print(f"✅ 已选择日期: {target_date}")
                    return True
            except:
                continue
        
        print(f"⚠️ 未找到日期 {day}")
        return False
        
    except Exception as e:
        print(f"❌ 日期选择错误: {e}")
        return False

def click_export(driver):
    """点击导出按钮"""
    try:
        # 切换到iframe
        iframe = driver.find_element(By.TAG_NAME, "iframe")
        driver.switch_to.frame(iframe)
        
        # 找到导出按钮
        export_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".el-button--primary"))
        )
        export_btn.click()
        print("✅ 已点击导出按钮")
        
        driver.switch_to.default_content()
        return True
        
    except Exception as e:
        print(f"❌ 导出失败: {e}")
        driver.switch_to.default_content()
        return False

def main():
    """主函数"""
    print("=" * 50)
    print("电力市场数据自动下载工具 (Selenium)")
    print("=" * 50)
    
    # 创建下载目录
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print(f"下载目录: {DOWNLOAD_DIR}")
    
    print("\n启动Chrome浏览器...")
    driver = setup_driver()
    
    try:
        url = "https://spot.poweremarket.com/uptspot/sr/mp/portaladmin/index.html#/"
        print(f"打开网页: {url}")
        driver.get(url)
        time.sleep(5)
        
        print("\n请手动操作:")
        print("1. 登录 (如需要)")
        print("2. 导航到: 我的交易 -> 实时交易 -> 实时节点电价查询")
        print("3. 选择区域: 云南")
        input("完成后按回车继续...")
        
        # 生成日期列表
        start = datetime.strptime(START_DATE, "%Y-%m-%d")
        end = datetime.strptime(END_DATE, "%Y-%m-%d")
        
        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        
        print(f"\n待下载: {len(dates)} 天 ({START_DATE} ~ {END_DATE})")
        
        for i, date in enumerate(dates):
            print(f"\n[{i+1}/{len(dates)}] 下载: {date}")
            
            if not select_date(driver, date):
                continue
            
            time.sleep(WAIT_LOAD)
            click_export(driver)
            time.sleep(WAIT_CLICK)
        
        print("\n" + "=" * 50)
        print("完成!")
        print(f"文件位置: {DOWNLOAD_DIR}")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        
    finally:
        input("\n按回车关闭浏览器...")
        driver.quit()

if __name__ == "__main__":
    main()
