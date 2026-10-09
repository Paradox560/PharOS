"""Record the real local demo UI; no request stubs, overlays or external writes."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT = Path(__file__).resolve().parents[2] / 'artifacts'

async def record():
    OUTPUT.mkdir(exist_ok=True)
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(channel='chrome', headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    context = await browser.new_context(viewport={'width': 1440, 'height': 900}, record_video_dir=str(OUTPUT / 'recording-raw'), record_video_size={'width': 1440, 'height': 900}, device_scale_factor=1)
    page = await context.new_page()
    page.set_default_timeout(10000)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        await page.goto('http://127.0.0.1:8765/', wait_until='domcontentloaded')
        await page.get_by_text('PharOS API connected', exact=True).wait_for()
        await page.wait_for_timeout(5000)
        await page.get_by_role('button', name='Possible lane obstruction', exact=False).click()
        await page.wait_for_timeout(2000)
        await page.locator('.evidence-moment').filter(has_text='00:08').click()
        await page.locator('.evidence-player').evaluate('(element) => element.scrollIntoView({block: "start", behavior: "smooth"})')
        await page.wait_for_timeout(3000)
        await page.get_by_role('button', name='Play evidence', exact=True).click()
        await page.wait_for_timeout(3000)
        await page.get_by_role('button', name='Pause evidence', exact=True).click()
        await page.get_by_role('slider', name='Evidence time').fill('12')
        await page.wait_for_timeout(2000)
        await page.get_by_role('button', name='Traffic forecasts', exact=True).click()
        await page.get_by_role('button', name='Run forecast', exact=True).click()
        await page.get_by_text('Speed outlook', exact=True).wait_for()
        await page.get_by_text('Speed outlook', exact=True).evaluate('(element) => element.scrollIntoView({block: "start", behavior: "smooth"})')
        await page.wait_for_timeout(4000)
        await page.locator('.nav-rail').get_by_role('button', name='Scenario lab', exact=True).click()
        await page.locator('.inspector-scroll').evaluate('(element) => element.scrollTop = 0')
        await page.wait_for_timeout(2000)
        await page.get_by_role('button', name='Run comparison', exact=True).click()
        await page.get_by_text('Scenario results', exact=True).wait_for(timeout=12000)
        await page.get_by_text('Scenario results', exact=True).evaluate('(element) => element.scrollIntoView({block: "start", behavior: "smooth"})')
        await page.wait_for_timeout(4000)
        await page.get_by_role('button', name='Play simulation replay', exact=True).scroll_into_view_if_needed()
        await page.get_by_role('slider', name='Simulation replay time', exact=True).fill('18')
        await page.get_by_role('button', name='Play simulation replay', exact=True).click()
        await page.wait_for_timeout(4000)
        await page.get_by_role('button', name='Baseline + late', exact=True).click()
        await page.wait_for_timeout(4000)
        await page.get_by_role('button', name='Pause simulation replay', exact=True).click()
        await page.screenshot(path=str(OUTPUT / 'pharos-design-demo-scenario.png'))
        await page.locator('.inspector-tabs').get_by_role('button', name='Brief', exact=True).click()
        await page.locator('.inspector-scroll').evaluate('(element) => element.scrollTop = 0')
        await page.get_by_role('button', name='Generate operator brief', exact=True).click()
        await page.locator('.answer-block').wait_for()
        await page.locator('.answer-block').evaluate('(element) => element.scrollIntoView({block: "start", behavior: "smooth"})')
        await page.wait_for_timeout(5000)
        assert not errors, errors
        await page.screenshot(path=str(OUTPUT / 'pharos-design-demo-final.png'))
        print('Recorded map, evidence seek/play, illustrative forecast, actual SUMO comparison/replay, and operator brief.', flush=True)
        print(f'Browser page errors: {len(errors)}', flush=True)
    finally:
        video = page.video
        await asyncio.wait_for(context.close(), timeout=10)
        if video:
            await video.save_as(str(OUTPUT / 'pharos-design-demo.webm'))
            print(str(OUTPUT / 'pharos-design-demo.webm'), flush=True)
        try:
            await asyncio.wait_for(browser.close(), timeout=5)
        except TimeoutError:
            print('Recording finalized; Chrome driver shutdown timed out.', flush=True)
        try:
            await asyncio.wait_for(pw.stop(), timeout=3)
        except TimeoutError:
            print('Recording finalized; Playwright shutdown timed out.', flush=True)

asyncio.run(asyncio.wait_for(record(), timeout=65))
