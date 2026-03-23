#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电力数据自动下载 - 完全自动化版本
使用JavaScript直接设置日期值
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
START_DATE = "2026-01-12"
END_DATE = "2026-02-01"
WAIT_LOAD = 12  # 等待数据加载
WAIT_BETWEEN = 3  # 日期间隔

def setup_driver():
    """连接到已运行的Chrome"""
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = webdriver.Chrome(options=chrome_options)
    driver.implicitly_wait(10)
    return driver

def set_date_via_js(driver, date_str):
    """
    使用JavaScript直接设置日期值
    这是关键：绕过日历UI，直接设置值并触发事件
    """
    try:
        # 找到日期输入框
        date_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="选择日期"]')
        
        # 使用JavaScript直接设置值
        driver.execute_script("""
            var input = arguments[0];
            input.value = arguments[1];
            // 触发事件
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            input.dispatchEvent(new Event('blur', { bubbles: true }));
        """, date_input, date_str)
        
        print(f"✅ 日期设置为: {date_str}")
        return True
        
    except Exception as e:
        print(f"❌ 日期设置失败: {e}")
        return False

def wait_for_export_ready(driver):
    """等待导出按钮可用"""
    try:
        # 切换到iframe
        iframe = driver.find_element(By.TAG_NAME, "iframe")
        driver.switch_to.frame(iframe)
        
        # 等待导出按钮可见且可点击
        export_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".el-button--primary"))
        )
        
        # 检查按钮是否启用（不是禁用状态）
        is_disabled = export_btn.get_attribute("disabled")
        if is_disabled:
            print("⏳ 导出按钮未启用，等待...")
            driver.switch_to.default_content()
            return False
        
        driver.switch_to.default_content()
        return True
        
    except Exception as e:
        driver.switch_to.default_content()
        return False

def click_export(driver):
    """点击导出按钮"""
    try:
        iframe = driver.find_element(By.TAG_NAME, "iframe")
        driver.switch_to.frame(iframe)
        
        export_btn = driver.find_element(By.CSS_SELECTOR, ".el-button--primary")
        export_btn.click()
        print("✅ 导出成功")
        
        driver.switch_to.default_content()
        return True
        
    except Exception as e:
        print(f"❌ 导出失败: {e}")
        driver.switch_to.default_content()
        return False

def verify_date_changed(driver, expected_date):
    """验证日期是否真的改变了"""
    try:
        date_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="选择日期"]')
        current_value = date_input.get_attribute("value")
        
        if current_value == expected_date:
            return True
        else:
            print(f"⚠️ 日期未改变: 期望 {expected_date}, 实际 {current_value}")
            return False
    except:
        return False

def main():
    print("=" * 50)
    print("电力数据自动下载 - 完全自动化")
    print("=" * 50)
    
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print(f"目录: {DOWNLOAD_DIR}")
    
    print("\n请确保Chrome已开启调试端口:")
    print('  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222')
    print("\n并在浏览器中:")
    print("1. 登录电力市场网站")
    print("2. 导航到【实时节点电价查询】")
    print("3. 选择区域: 云南")
    print("\n完成后按回车开始自动下载...")
    input()
    
    driver = setup_driver()
    
    try:
        # 确认在正确页面
        print(f"\n当前URL: {driver.current_url}")
        
        # 生成日期列表
        start = datetime.strptime(START_DATE, "%Y-%m-%d")
        end = datetime.strptime(END_DATE, "%Y-%m-%d")
        
        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        
        print(f"\n待下载: {len(dates)} 天")
        print(f"范围: {START_DATE} ~ {END_DATE}")
        print("-" * 40)
        
        # 逐个下载
        for i, date in enumerate(dates):
            print(f"\n[{i+1}/{len(dates)}] {date}")
            
            # 设置日期
            if not set_date_via_js(driver, date):
                print("❌ 跳过")
                continue
            
            # 等待数据加载
            print(f"等待 {WAIT_LOAD} 秒...")
            time.sleep(WAIT_LOAD)
            
            # 检查日期是否真的改变了
            if not verify_date_changed(driver, date):
                print("⚠️ 日期验证失败，尝试刷新...")
                driver.refresh()
                time.sleep(3)
                continue
            
            # 等待导出按钮启用
            ready = False
            for _ in range(3):  # 最多重试3次
                if wait_for_export_ready(driver):
                    ready = True
                    break
                time.sleep(5)
            
            if not ready:
                print("⏳ 导出按钮未就绪，跳过")
                continue
            
            # 导出
            click_export(driver)
            
            # 间隔
            time.sleep(WAIT_BETWEEN)
        
        print("\n" + "=" * 50)
        print("下载完成!")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        
    finally:
        input("\n按回车退出...")
        driver.quit()

if __name__ == "__main__":
    main()
