import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const b = await chromium.launch();
for (const [scale,out] of [[1,'linkedin-cover.png'],[2,'linkedin-cover@2x.png']]) {
  const p = await b.newPage({viewport:{width:1584,height:396},deviceScaleFactor:scale});
  await p.goto('file://'+process.cwd()+'/cover.html',{waitUntil:'networkidle'});
  await p.evaluate(()=>document.fonts.ready);
  console.log(await p.evaluate(()=>[...document.fonts].filter(f=>f.status==='loaded').map(f=>f.family).join(',')));
  await p.screenshot({path:out});
}
await b.close();
