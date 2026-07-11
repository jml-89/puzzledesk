// Screenshot a rendered site/ page, so "did it render?" is one command instead of a
// fumble through Playwright's module path and the browser binary.
//
//   node site/preview.cjs midi-long.html                  -> site/preview.png
//   node site/preview.cjs index.html shots/index.png      -> custom output
//   node site/preview.cjs midi-long.html out.png --reveal -> click Reveal first
//
// Notes for the hosted (Claude Code on the web) environment: Playwright is installed
// globally, not in this repo, and the browser lives under PLAYWRIGHT_BROWSERS_PATH
// (=/opt/pw-browsers) -- so we resolve the module by trying a few known locations and
// let Playwright find the browser itself (do NOT hardcode the versioned chromium path;
// it changes with the Playwright version). Run `render_pages.py` first to (re)build pages.

const path = require('path');

function loadPlaywright() {
  const candidates = [
    'playwright',                                   // local install, if one ever exists
    '/opt/node22/lib/node_modules/playwright',      // hosted global (Claude Code on web)
    '/usr/lib/node_modules/playwright',
    '/usr/local/lib/node_modules/playwright',
  ];
  for (const c of candidates) {
    try { return require(c); } catch { /* try next */ }
  }
  console.error('Playwright not found. Install it (npm i -D playwright) or set the module path.');
  process.exit(1);
}

(async () => {
  const args = process.argv.slice(2);
  const reveal = args.includes('--reveal');
  const positional = args.filter((a) => !a.startsWith('--'));
  const page = positional[0] || 'index.html';
  const out = positional[1] || path.join(__dirname, 'preview.png');
  const file = path.isAbsolute(page) ? page : path.join(__dirname, page);

  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();          // browser resolved via PLAYWRIGHT_BROWSERS_PATH
  const p = await browser.newPage({ viewport: { width: 1100, height: 980 } });
  await p.goto('file://' + file);
  await p.waitForTimeout(400);
  if (reveal) { await p.click('#revealBtn'); await p.waitForTimeout(300); }
  await p.screenshot({ path: out });
  await browser.close();
  console.log('wrote ' + out + (reveal ? ' (revealed)' : ''));
})().catch((e) => { console.error(e.message); process.exit(1); });
