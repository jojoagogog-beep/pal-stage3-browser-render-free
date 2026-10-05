import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import {mkdir,readFile} from 'node:fs/promises';
const base='http://127.0.0.1:3100';
await mkdir('docs/media',{recursive:true});
const browser=await chromium.launch({channel:'chromium',headless:true});
try {
const page=await browser.newPage({viewport:{width:1600,height:900},deviceScaleFactor:1});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
for(const [state,file] of [['all','01-review'],['missing-alt','02-image-evidence'],['heading-skip','03-heading-structure'],['generic-link','04-link-purpose'],['worklist','05-team-worklist']]){
 await page.goto(`${base}/media-preview?state=${state}`);await page.getByRole('heading',{level:1}).waitFor();await page.evaluate(()=>document.fonts.ready);
 await page.screenshot({path:`docs/media/${file}.png`});
 assert.equal(await page.locator('body').evaluate(el=>el.scrollWidth<=1600),true);
}
await page.goto(`${base}/review-demo`);
await page.getByRole('button',{name:'Generic link text',exact:true}).click();
assert.equal(await page.locator('pre').innerText(),'<a href="/pages/care">Click here</a>');
await page.getByRole('searchbox').fill('No such product');
await page.getByRole('heading',{name:'No matching findings'}).waitFor();
await page.getByRole('searchbox').fill('Ceramic');
const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'Export filtered CSV'}).click();
const download=await downloadPromise;await download.saveAs('docs/media/demo-worklist.csv');
const csv=await readFile('docs/media/demo-worklist.csv','utf8');assert.match(csv,/Generic link text/);assert.doesNotMatch(csv,/Image missing alt/);
for(const [state,heading] of [['empty','Your catalog is empty'],['clean','No issues detected by these checks']]){await page.goto(`${base}/review-demo?state=${state}`);await page.getByRole('heading',{name:heading}).waitFor();}
for(const route of ['privacy','terms','support']){const response=await page.goto(`${base}/${route}`);assert.equal(response.status(),200);}
await page.setViewportSize({width:390,height:844});await page.goto(`${base}/review-demo`);assert.equal(await page.locator('body').evaluate(el=>el.scrollWidth<=390),true);
assert.deepEqual(errors,[]);console.log('UI checks passed: filters, escaped evidence, CSV download, empty/clean states, public pages, mobile width; 5 screenshots captured.');
} finally {await browser.close();}
