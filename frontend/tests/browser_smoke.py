"""Local-only UI checks. Run after API startup; screenshots stay in ignored artifacts/."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    output = Path(__file__).resolve().parents[1] / 'artifacts'
    output.mkdir(exist_ok=True)
    errors = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel='chrome', headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        page = await browser.new_page(viewport={'width': 390, 'height': 844}, device_scale_factor=1)
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto('http://127.0.0.1:8765/', wait_until='domcontentloaded')
        await page.get_by_text('PharOS API connected', exact=True).wait_for()
        await page.get_by_text('OpenFreeMap · vector map', exact=True).wait_for(timeout=30000)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile document overflows'
        await page.screenshot(path=str(output / 'mobile-map.png'))
        await page.locator('.mobile-switcher').get_by_role('button', name='sources', exact=True).click()
        await page.get_by_role('button', name='Possible lane obstruction', exact=False).click()
        await page.get_by_role('heading', name='Possible lane obstruction').wait_for()
        await page.get_by_role('slider', name='Evidence time').fill('8')
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(output / 'mobile-evidence.png'))
        assert await page.locator('.detection-box').count() == 1, 'Fixture detection must align at 8s'
        await page.get_by_role('button', name='Traffic forecasts', exact=True).click()
        await page.get_by_role('button', name='Run forecast', exact=True).click()
        await page.get_by_text('Speed outlook', exact=True).wait_for()
        await page.screenshot(path=str(output / 'mobile-forecast.png'))
        await page.get_by_role('button', name='Connection details and preferences', exact=True).click()
        await page.get_by_role('heading', name='Know what’s connected.').wait_for()
        await page.screenshot(path=str(output / 'mobile-providers.png'))
        await page.get_by_role('button', name='Close connection center', exact=True).click()
        await page.set_viewport_size({'width': 768, 'height': 1024})
        await page.screenshot(path=str(output / 'tablet-forecast.png'))
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Tablet document overflows'
        assert not errors, errors
        print('Mobile + tablet layout, evidence seek/box, illustrative forecast, connection dialog: passed.')
        await browser.close()

asyncio.run(main())
