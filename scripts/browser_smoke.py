"""Exercise the running console with an isolated browser; save review screenshots."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--chrome', default='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    parser.add_argument('--out', default='artifacts')
    args = parser.parse_args()
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chrome if Path(args.chrome).exists() else None, headless=True)
        page = browser.new_page(viewport={'width':1600,'height':1060}, device_scale_factor=1)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until='networkidle')
        expect(page.get_by_text('DEMO', exact=True)).to_be_visible()
        expect(page.locator('.maplibregl-canvas')).to_be_visible()
        page.screenshot(path=str(output/'01-console.png'), full_page=True)
        page.locator('.evidence-spans button').first.click()
        page.wait_for_function('document.querySelector("video").currentTime >= 8')
        expect(page.locator('.detection-box')).to_have_count(1)
        page.get_by_role('button',name='Toggle detection boxes').click()
        expect(page.locator('.detection-box')).to_have_count(0)
        page.get_by_role('button',name='Toggle detection boxes').click()
        search = page.get_by_role('textbox',name='Search archive footage')
        search.fill('lane obstruction')
        search.press('Enter')
        expect(page.get_by_text('Demo keyword fallback (not semantic search)', exact=True)).to_be_visible()
        page.locator('.search-card').first.click()
        page.wait_for_function('document.querySelector("video").currentTime >= 8')
        page.screenshot(path=str(output/'02-evidence.png'), full_page=True)
        page.get_by_role('button',name='Traffic forecasts', exact=True).click()
        page.get_by_role('button',name='Run forecast',exact=True).click()
        expect(page.get_by_text('Speed outlook',exact=True)).to_be_visible()
        expect(page.locator('.forecast-values')).to_be_visible()
        page.screenshot(path=str(output/'03-forecast.png'), full_page=True)
        page.get_by_role('button',name='Scenario lab',exact=True).first.click()
        page.get_by_role('button',name='Run comparison',exact=True).click()
        expect(page.get_by_text('Scenario results',exact=True)).to_be_visible(timeout=60000)
        expect(page.get_by_text('Synchronized map replay',exact=True)).to_be_visible()
        slider = page.get_by_role('slider',name='Simulation replay time')
        slider.fill('30')
        page.get_by_role('button',name='Baseline + late',exact=True).click()
        page.screenshot(path=str(output/'04-simulation.png'), full_page=True)
        page.locator('.inspector-tabs').get_by_role('button',name='Brief',exact=True).click()
        page.get_by_role('button',name='Generate operator brief',exact=True).click()
        expect(page.get_by_text('Deterministic demo template',exact=True)).to_be_visible()
        expect(page.locator('.evidence-references button').first).to_be_visible()
        page.screenshot(path=str(output/'05-brief.png'), full_page=True)
        page.get_by_role('button',name='Connection details and preferences',exact=True).click()
        expect(page.get_by_role('dialog')).to_be_visible()
        page.get_by_role('button',name='Close connection center').click()
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_timeout(600)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), 'Mobile overflow'
        page.screenshot(path=str(output/'06-mobile.png'),full_page=True)
        assert not errors, errors
        (output/'browser-verification.json').write_text(json.dumps({'page_errors':errors,'workflow':['3D map','seek + detection toggle','search + exact span','forecast','SUMO comparison + replay','cited brief','provider dialog','mobile viewport'],'status':'passed'},indent=2))
        browser.close()
    print('Browser workflow passed: 3D map, evidence, search, forecast, SUMO, brief, dialog, mobile.')


if __name__ == '__main__':
    main()
