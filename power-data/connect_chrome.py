#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
连接到已运行的Chrome浏览器
用户手动选择日期，脚本自动导出
"""

import os
import time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# 配置
DOWNLOAD_DIR = os.path.expanduser("~/Downloads/电力数据")
DEBUG_PORT = 9222

def connect_to_chrome():
    """连接到已运行的Chrome"""
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        print(f"连接失败: {e}")
        print("\n请先在Windows上运行:")
        print(r'"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222')
        return None

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
        print("✅ 导出成功!")
        
        driver.switch_to.default_content()
        return True
        
    except Exception as e:
        print(f"❌ 导出失败: {e}")
        driver.switch_to.default_content()
        return False

def main():
    print("=" * 50)
    print("连接到已运行的Chrome浏览器")
    print("=" * 50)
    
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print(f"下载目录: {DOWNLOAD_DIR}")
    print("\n请确保:")
    print("1. Chrome已打开 (带 --remote-debugging-port=9222 参数)")
    print("2. 已登录电力市场网站")
    print("3. 已导航到【实时节点电价查询】页面")
    print("4. 已选择要下载的日期")
    print("\n完成后按回车继续导出...")
    
    input()
    
    driver = connect_to_chrome()
    if not driver:
        return
    
    try:
        # 获取当前URL确认在正确页面
        print(f"\n当前页面: {driver.current_url}")
        
        # 检查日期
        try:
            date_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="选择日期"]')
            print(f"当前日期: {date_input.get_attribute('value')}")
        except:
            pass
        
        # 点击导出
        print("\n点击导出按钮...")
        if click_export(driver):
            print("✅ 数据导出成功!")
        else:
            print("❌ 导出失败，请检查页面")
        
    except Exception as e:
        print(f"错误: {e}")
        
    finally:
        input("\n按回车退出...")
        driver.quit()

if __name__ == "__main__":
    main()
