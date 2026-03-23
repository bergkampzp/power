#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电力数据自动下载 - Playwright完整版
连接到Browser Relay，自动完成日期选择和导出
"""

import asyncio
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# 配置
START_DATE = "2026-01-12"
END_DATE = "2026-02-01"
DEBUG_PORT = 18792
WAIT_LOAD = 12  # 等待数据加载秒数
WAIT_BETWEEN = 3  # 日期间隔秒数

async def set_date(page, date_str):
    """使用JavaScript设置日期"""
    try:
        # 点击日期输入框激活
        await page.click('input[placeholder="选择日期"]')
        await asyncio.sleep(0.5)
        
        # 使用JS设置值并触发事件
        await page.evaluate('''
            () => {
                const input = document.querySelector('input[placeholder="选择日期"]');
                input.value = arguments[0];
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.dispatchEvent(new Event('blur', { bubbles: true }));
            }
        ''', date_str)
        
        print(f"  ✅ 日期设置为: {date_str}")
        return True
    except Exception as e:
        print(f"  ❌ 日期设置失败: {e}")
        return False

async def wait_for_export_ready(page):
    """等待导出按钮就绪"""
    try:
        # 等待iframe加载
        await page.wait_for_selector('iframe', timeout=5000)
        
        # 获取第一个iframe
        frame = page.frame_locator('iframe')
        
        # 等待导出按钮
        await frame.wait_for_selector('.el-button--primary', timeout=10000)
        
        # 检查按钮是否启用
        btn = await frame.query_selector('.el-button--primary')
        is_disabled = await btn.get_attribute('disabled')
        
        if is_disabled:
            return False
        return True
    except:
        return False

async def click_export(page):
    """点击导出按钮"""
    try:
        frame = page.frame_locator('iframe')
        await frame.click('.el-button--primary')
        print("  ✅ 导出成功")
        return True
    except Exception as e:
        print(f"  ❌ 导出失败: {e}")
        return False

async def verify_date(page, expected_date):
    """验证日期是否正确"""
    try:
        input_elem = await page.query_selector('input[placeholder="选择日期"]')
        current = await input_elem.get_attribute('value')
        return current == expected_date
    except:
        return False

async def download_date_range():
    """下载日期范围"""
    print("=" * 50)
    print("电力数据自动下载 - Playwright版")
    print("=" * 50)
    
    # 生成日期列表
    start = datetime.strptime(START_DATE, "%Y-%m-%d")
    end = datetime.strptime(END_DATE, "%Y-%m-%d")
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    
    print(f"待下载: {len(dates)} 天 ({START_DATE} ~ {END_DATE})")
    print("-" * 50)
    
    async with async_playwright() as p:
        try:
            # 连接到Browser Relay
            print(f"连接到 localhost:{DEBUG_PORT}...")
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
            
            # 获取页面
            if browser.contexts[0].pages:
                page = browser.contexts[0].pages[0]
            else:
                print("❌ 没有找到页面")
                return
            
            print(f"✅ 已连接: {page.url[:50]}...")
            
            # 逐个下载
            for i, date in enumerate(dates):
                print(f"\n[{i+1}/{len(dates)}] {date}")
                
                # 设置日期
                if not await set_date(page, date):
                    continue
                
                # 等待数据加载
                print(f"  等待加载 {WAIT_LOAD}秒...")
                await asyncio.sleep(WAIT_LOAD)
                
                # 验证日期
                if not await verify_date(page, date):
                    print(f"  ⚠️ 日期验证失败")
                    # 刷新重试
                    await page.reload()
                    await asyncio.sleep(3)
                    continue
                
                # 等待导出就绪
                ready = False
                for _ in range(3):
                    if await wait_for_export_ready(page):
                        ready = True
                        break
                    await asyncio.sleep(5)
                
                if not ready:
                    print(f"  ⏳ 导出按钮未就绪")
                    continue
                
                # 导出
                await click_export(page)
                
                # 间隔
                await asyncio.sleep(WAIT_BETWEEN)
            
            print("\n" + "=" * 50)
            print("下载完成!")
            
        except Exception as e:
            print(f"❌ 错误: {e}")
            
        finally:
            await browser.close()

async def test_single_date():
    """测试单个日期"""
    print("测试模式: 下载 2026-01-13")
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
            page = browser.contexts[0].pages[0]
            print(f"当前: {page.url[:50]}")
            
            # 设置日期
            await set_date(page, "2026-01-13")
            
            # 等待
            print("等待10秒...")
            await asyncio.sleep(10)
            
            # 导出
            print("点击导出...")
            if await wait_for_export_ready(page):
                await click_export(page)
            else:
                print("导出按钮未就绪")
            
        except Exception as e:
            print(f"错误: {e}")
            
        finally:
            await browser.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(test_single_date())
    else:
        asyncio.run(download_date_range())
