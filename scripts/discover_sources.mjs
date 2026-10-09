/** Auditable, public-only browser discovery. No auth, no image/video collection.
 * Usage: PLAYWRIGHT_MODULE=/path/to/playwright-core/index.mjs CHROMIUM_EXECUTABLE=/path/to/chrome node scripts/discover_sources.mjs [output-dir]
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';

const modulePath = process.env.PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = await import(modulePath.startsWith('/') ? pathToFileURL(modulePath) : modulePath);
const output = path.resolve(process.argv[2] || 'data/source-discovery');
await fs.mkdir(output, {recursive: true});
const sourceUrl = 'https://webcams.nyctmc.org/cameras-list';
const audit = {source_url: sourceUrl, started_at: new Date().toISOString(), engine: 'playwright', responses: [], errors: []};
let browser;
try {
  browser = await chromium.launch({headless: true, ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath:process.env.CHROMIUM_EXECUTABLE} : {})});
  const page = await browser.newPage();
  const pending = [];
  // Routine snapshots are intentionally excluded; discovery records metadata only.
  await page.route('**/api/cameras/*/image*', route => route.abort());
  page.on('response', response => {
    if (new URL(response.url()).hostname !== 'webcams.nyctmc.org' || !response.url().includes('graphql')) return;
    pending.push((async () => {
      const body = await response.text();
      const record = {url: response.url(), status: response.status(), observed_at: new Date().toISOString(), request: response.request().postDataJSON(), body_sha256:createHash('sha256').update(body).digest('hex')};
      try {record.body = JSON.parse(body);} catch {record.body_excerpt = body.slice(0,300);}
      audit.responses.push(record);
    })().catch(e => audit.errors.push(e.message)));
  });
  await page.goto(sourceUrl, {waitUntil:'networkidle', timeout:45000});
  audit.title = await page.title();
  audit.rendered_text = (await page.locator('body').first().innerText()).slice(0,30000);
  await page.screenshot({path:path.join(output, 'camera-list.png'), fullPage:true});
  // Map renders public catalog coordinate data that the list omits.
  const map = page.getByRole('link', {name:'Map', exact:true});
  if (await map.count()) {
    await map.first().click();
    await page.waitForLoadState('networkidle');
  } else {
    await page.goto('https://webcams.nyctmc.org/', {waitUntil:'networkidle', timeout:45000});
  }
  await Promise.all(pending);
  audit.completed_at = new Date().toISOString();
  audit.status = 'succeeded';
} catch(e) {
  audit.status = 'failed';
  audit.errors.push(String(e.message).slice(0,5000));
  process.exitCode = 1;
} finally {
  if(browser) await browser.close();
  await fs.writeFile(path.join(output, 'audit.json'), JSON.stringify(audit,null,2));
  console.log(JSON.stringify({status:audit.status, output, responses:audit.responses.length, errors:audit.errors}));
}
