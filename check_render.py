"""Check page rendering with Playwright"""
import asyncio
from playwright.async_api import async_playwright

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.on('console', lambda msg: print(f'[CONSOLE] {msg.type}: {msg.text}'))
        page.on('pageerror', lambda err: print(f'[ERROR] {err}'))
        try:
            await page.goto('http://localhost:8898/', timeout=15000)
            await page.wait_for_load_state('networkidle', timeout=10000)
            await asyncio.sleep(2)  # wait for React to render
            content = await page.content()
            if '热点地图' in content:
                print('SUCCESS: Page rendered with 热点地图')
                # Also check the body has actual content
                inner = await page.inner_html('#root')
                print(f'Root inner HTML length: {len(inner)}')
                if len(inner) < 100:
                    print('Root content seems empty, checking for errors...')
                    print(inner[:500])
            else:
                print(f'FAIL: Page rendered but no 热点地图 found')
                print(f'Content length: {len(content)}')
                print(content[:1000])
        except Exception as e:
            print(f'EXCEPTION: {e}')
        await browser.close()

asyncio.run(check())
