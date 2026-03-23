#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电力市场数据自动下载 - Selenium + Edge
"""

import os
import time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# 配置
DOWNLOAD_DIR = os.path.expanduser("~/Downloads/电力数据")
START_DATE = "2026-01-12"
END_DATE = "2026-02-01"
WAIT_LOAD = 10
WAIT_CLICK = 3

def setup_driver():
    """设置Edge驱动"""
    edge_options = Options()
    
    # 添加下载路径
    prefs = {
        "download.default_directory": DOWNLOAD_DIR.replace("/", "\\"),
        "download.prompt_for_download": False,
    }
    edge_options.add_experimental_option("prefs", prefs)
    edge_options.add_argument("--start-maximized")
    
    try:
        service = Service(EdgeChromiumDriverManager().install())
        driver = webdriver.Edge(service=service, options=edge_options)
    except:
        driver = webdriver.Edge(options=edge_options)
    
    driver.implicitly_wait(10)
    return driver

def select_date(driver, target_date):
    """选择日期"""
    try:
        date_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="选择日期"]')
        date_input.click()
        time.sleep(1)
        
        day = int(target_date.split("-")[2])
        cells = driver.find_elements(By.CSS_SELECTOR, ".el-date-table td span:not(.disabled)")
        
        for cell in cells:
            try:
                if cell.text == str(day):
                    cell.click()
                    print(f"✅ {target_date}")
                    return True
            except:
                continue
        return False
    except Exception as e:
        print(f"❌ {e}")
        return False

def click_export(driver):
    """点击导出"""
    try:
        iframe = driver.find_element(By.TAG_NAME, "iframe")
        driver.switch_to.frame(iframe)
        
        export_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".el-button--primary"))
        )
        export_btn.click()
        print("✅ 导出")
        
        driver.switch_to.default_content()
        return True
    except Exception as e:
        print(f"❌ {e}")
        driver.switch_to.default_content()
        return False

def main():
    print("=" * 40)
    print("电力数据自动下载 (Edge)")
    print("=" * 40)
    
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print(f"目录: {DOWNLOAD_DIR}")
    
    driver = setup_driver()
    
    try:
        driver.get("https://spot.poweremarket.com/uptspot/sr/mp/portaladmin/index.html#/")
        time.sleep(5)
        
        print("\n请手动登录并导航到【实时节点电价查询】页面")
        print("完成后切换回此窗口按回车...")
        input()
        
        # 日期列表
        start = datetime.strptime(START_DATE, "%Y-%m-%d")
        end = datetime.strptime(END_DATE, "%Y-%m-%d")
        dates = []
        while start <= end:
            dates.append(start.strftime("%Y-%m-%d"))
            start += timedelta(days=1)
        
        print(f"\n开始下载 {len(dates)} 天数据...")
        
        for i, date in enumerate(dates):
            print(f"[{i+1}/{len(dates)}] {date}")
            if select_date(driver, date):
                time.sleep(WAIT_LOAD)
                click_export(driver)
                time.sleep(WAIT_CLICK)
        
        print("\n完成!")
        
    except Exception as e:
        print(f"错误: {e}")
        
    finally:
        input("回车退出...")
        driver.quit()

if __name__ == "__main__":
    main()
