"""Independent local UI review; writes screenshots/results, never contacts the workshop VM.

Run: .venv/bin/python frontend/tests/design_review.py
The motion check reads MapLibre's public camera API through the existing React ref;
it does not patch application code or mock map/provider responses.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[2]


async def review(args):
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    results = {"url": args.url, "checks": [], "page_errors": [], "screenshots": [], "notes": []}

    async def check(name, action):
        started = time.monotonic()
        try:
            detail = await action()
            results["checks"].append({"name": name, "status": "passed", "detail": detail, "elapsed_ms": round((time.monotonic() - started) * 1000)})
        except Exception as error:
            results["checks"].append({"name": name, "status": "failed", "error": str(error)[:1800]})
        print(json.dumps(results["checks"][-1]), flush=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(viewport={"width": 1600, "height": 1060}, device_scale_factor=1)
        page = await context.new_page()
        page.set_default_timeout(6000)
        page.on("pageerror", lambda error: results["page_errors"].append(str(error)))
        try:
            await page.goto(args.url, wait_until="domcontentloaded")
            await expect(page.get_by_text("PharOS API connected", exact=True)).to_be_visible()
            await expect(page.get_by_text("OpenFreeMap · vector map", exact=True)).to_be_visible(timeout=30000)

            async def screenshot(name):
                path = output / name
                await page.screenshot(path=str(path), full_page=True)
                results["screenshots"].append(str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path))

            async def overflow():
                sizes = await page.evaluate("""() => ({width:innerWidth, documentWidth:document.documentElement.scrollWidth, bodyWidth:document.body.scrollWidth,
                  overflow: [...document.querySelectorAll('header, .workspace-header, .mobile-switcher, .source-panel, .inspector-panel, .inspector-tabs, .map-topbar')].filter(el => el.getClientRects().length).filter(el => {const r=el.getBoundingClientRect();return r.left < -1 || r.right > innerWidth+1}).map(el => ({element:el.className,width:el.getBoundingClientRect().width,left:el.getBoundingClientRect().left}))})""")
                assert sizes["documentWidth"] <= sizes["width"] + 1 and sizes["bodyWidth"] <= sizes["width"] + 1 and not sizes["overflow"], sizes
                return sizes

            async def layers():
                trigger = page.get_by_role("button", name="Toggle map layers", exact=True)
                await trigger.focus()
                await trigger.press("Enter")
                group = page.get_by_role("group", name="Map layers", exact=True)
                await expect(group).to_be_visible()
                await expect(group.get_by_role("checkbox").first).to_be_focused()
                await page.keyboard.press("Escape")
                await expect(group).not_to_be_visible()
                assert await trigger.evaluate("el => el === document.activeElement"), {"step": "escape_focus", "active": await page.evaluate("document.activeElement.outerHTML.slice(0,300)")}
                await trigger.click()
                await page.locator(".map-location strong").click()
                await expect(group).not_to_be_visible()
                await expect(trigger).to_be_focused(timeout=1500)
                await trigger.click()
                cameras = group.get_by_role("checkbox", name="Public camera locations", exact=True)
                await cameras.uncheck()
                await expect(page.locator(".legend-camera")).to_have_count(0)
                await cameras.check()
                await expect(page.locator(".legend-camera")).to_be_visible()
                await page.keyboard.press("Escape")
                return "Keyboard open, first-checkbox focus, Escape and outside close, trigger focus return, camera legend visibility"

            async def map_reference():
                found = await page.evaluate("""() => {
                  const el = document.querySelector('.map-canvas');
                  const key = Object.keys(el).find(key => key.startsWith('__reactFiber$'));
                  let fiber=el[key];
                  while(fiber) {
                    let hook=fiber.memoizedState;
                    while(hook && typeof hook === 'object') {
                      const candidate=hook.memoizedState?.current?.map;
                      if(candidate && typeof candidate.isMoving==='function' && typeof candidate.getZoom==='function') {window.__pharosReviewMap=candidate;return true;}
                      hook=hook.next;
                    }
                    fiber=fiber.return;
                  }
                  return false;
                }""")
                assert found, "Could not read public MapLibre camera API through the existing component ref."

            async def motion():
                await map_reference()
                await page.wait_for_function("!window.__pharosReviewMap.isMoving()")
                zoom = page.get_by_role("button", name="Zoom in", exact=True)
                before = await page.evaluate("window.__pharosReviewMap.getZoom()")
                await zoom.focus()
                await zoom.press("Enter")
                state = await page.evaluate("({zoom:window.__pharosReviewMap.getZoom(),moving:window.__pharosReviewMap.isMoving()})")
                assert state["zoom"] > before and not state["moving"], {"before": before, "after": state}
                canvas = page.locator("canvas.maplibregl-canvas")
                await canvas.focus()
                before_center = await page.evaluate("window.__pharosReviewMap.getCenter().toArray()")
                await canvas.press("ArrowRight")
                state = await page.evaluate("({center:window.__pharosReviewMap.getCenter().toArray(),moving:window.__pharosReviewMap.isMoving()})")
                assert state["center"] != before_center and not state["moving"], state
                await page.emulate_media(reduced_motion="reduce")
                await zoom.click()
                state = await page.evaluate("({moving:window.__pharosReviewMap.isMoving(),reduced:matchMedia('(prefers-reduced-motion:reduce)').matches,transition:getComputedStyle(document.querySelector('.map-icon')).transitionDuration})")
                assert state["reduced"] and not state["moving"] and all(float(part.strip().rstrip("s")) == 0 for part in state["transition"].split(",")), state
                await screenshot("02-reduced-motion.png")
                await page.emulate_media(reduced_motion="no-preference")
                await page.evaluate("""() => {
                  window.__pharosReviewMotion={};
                  window.__pharosReviewMap.once('movestart',()=>window.__pharosReviewMotion.start=performance.now());
                  window.__pharosReviewMap.once('moveend',()=>window.__pharosReviewMotion.end=performance.now());
                }""")
                await zoom.click()
                await page.wait_for_function("window.__pharosReviewMotion.end != null", timeout=1500)
                elapsed = await page.evaluate("Math.round(window.__pharosReviewMotion.end-window.__pharosReviewMotion.start)")
                return {"keyboard_zoom_and_pan_instant": True, "reduced_pointer_motion_instant": True, "pointer_map_motion_ms": elapsed}

            async def panels(width, height, label):
                await page.set_viewport_size({"width": width, "height": height})
                switcher = page.locator(".mobile-switcher")
                await switcher.get_by_role("button", name="Browse", exact=True).click()
                await expect(page.get_by_role("complementary", name="Sources and incident queue", exact=True)).to_be_visible()
                await expect(switcher.get_by_role("button", name="Browse", exact=True)).to_have_attribute("aria-pressed", "true")
                await overflow()
                await screenshot(f"{label}-browse.png")
                await switcher.get_by_role("button", name="Map", exact=True).click()
                await expect(page.locator(".map-workspace")).to_be_visible()
                await overflow()
                await screenshot(f"{label}-map.png")
                await switcher.get_by_role("button", name="Analysis", exact=True).click()
                await expect(page.locator(".inspector-scroll h2").first).to_be_focused()
                tabs = page.locator(".inspector-tabs")
                for tab in ["Evidence", "Forecast", "Scenario", "Brief"]:
                    button = tabs.get_by_role("button", name=tab, exact=True)
                    await button.click()
                    await expect(button).to_have_attribute("aria-pressed", "true")
                    await expect(page.locator(".inspector-scroll h2").first).to_be_visible()
                    await overflow()
                    if tab in {"Forecast", "Scenario"}:
                        primary = page.get_by_role("button", name="Run forecast" if tab == "Forecast" else "Run comparison", exact=True)
                        await primary.scroll_into_view_if_needed()
                        await expect(primary).to_be_visible()
                    await screenshot(f"{label}-{tab.lower()}.png")
                return "Browse/Map/Analysis reachable; all four analysis panels and their primary actions reachable; no horizontal overflow"

            async def panel_scroll_reset():
                await page.set_viewport_size({"width": 390, "height": 844})
                await page.locator(".mobile-switcher").get_by_role("button", name="Analysis", exact=True).click()
                tabs = page.locator(".inspector-tabs")
                await tabs.get_by_role("button", name="Scenario", exact=True).click()
                await page.locator(".inspector-scroll").evaluate("el => el.scrollTop = el.scrollHeight")
                await tabs.get_by_role("button", name="Forecast", exact=True).click()
                top = await page.locator(".inspector-scroll").evaluate("el => el.scrollTop")
                await screenshot("05-mobile-panel-switch.png")
                assert top <= 1, {"scrollTop_after_opening_forecast": top, "expected": "New panel starts at its heading and controls"}
                return {"scrollTop": top}

            async def text_resize():
                await page.set_viewport_size({"width": 390, "height": 844})
                await page.evaluate("document.documentElement.style.fontSize = `${parseFloat(getComputedStyle(document.documentElement).fontSize) * 2}px`")
                await page.locator(".mobile-switcher").get_by_role("button", name="Analysis", exact=True).click()
                failures = []
                for label in ["Evidence", "Forecast", "Scenario", "Brief"]:
                    try:
                        button = page.locator(".inspector-tabs").get_by_role("button", name=label, exact=True)
                        await button.click(timeout=2500)
                        box = await button.bounding_box()
                        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 391, box
                        await overflow()
                        if label in {"Forecast", "Scenario", "Brief"}:
                            action_name = {"Forecast": "Run forecast", "Scenario": "Run comparison", "Brief": "Generate operator brief"}[label]
                            action = page.get_by_role("button", name=action_name, exact=True)
                            await action.scroll_into_view_if_needed(timeout=2500)
                            await expect(action).to_be_visible()
                    except Exception as error:
                        failures.append({"panel": label, "error": str(error)[:700]})
                await screenshot("05-mobile-200-percent-text.png")
                await page.evaluate("document.documentElement.style.fontSize = ''")
                assert not failures, failures
                return "All four panels accessible at 200% root font size and 390px viewport"

            await check("desktop_no_overflow", overflow)
            await screenshot("01-desktop.png")
            await check("layers_keyboard_dismissal_and_legend", layers)
            await check("map_keyboard_and_reduced_motion", motion)
            await check("mobile_390_navigation", lambda: panels(390, 844, "03-mobile"))
            await check("tablet_768_navigation", lambda: panels(768, 1024, "04-tablet"))
            await check("panel_switch_scroll_reset", panel_scroll_reset)
            await check("mobile_200_percent_text", text_resize)
            assert not results["page_errors"], results["page_errors"]
        except Exception as error:
            results["fatal_error"] = str(error)
        finally:
            results["status"] = "passed" if not results["page_errors"] and not results.get("fatal_error") and all(check["status"] == "passed" for check in results["checks"]) else "failed"
            (output / "results.json").write_text(json.dumps(results, indent=2))
            print(json.dumps({"status": results["status"], "results": str(output / "results.json")}), flush=True)
            for resource in (page, context, browser):
                try:
                    await asyncio.wait_for(resource.close(), timeout=5)
                except TimeoutError:
                    print("A browser teardown step timed out after results were saved.", flush=True)
                except Exception:
                    pass
    return results["status"] == "passed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--out", default=str(ROOT / "artifacts" / "design-a11y"))
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(review(args)) else 1)
