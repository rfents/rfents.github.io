import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const b = await chromium.launch();
for (const name of process.argv.slice(2)) {
  for (const [scale,suffix] of [[1,''],[2,'@2x']]) {
    const p = await b.newPage({viewport:{width:1584,height:396},deviceScaleFactor:scale});
    await p.goto(`file://${process.cwd()}/cover-${name}.html`,{waitUntil:'networkidle'});
    await p.evaluate(()=>document.fonts.ready);
    await p.screenshot({path:`linkedin-cover-${name}${suffix}.png`});
  }
}
await b.close();
