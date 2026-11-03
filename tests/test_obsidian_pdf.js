const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../.local/share/underlight/obsidian/pdf-export-ready.js'), 'utf8');
function deferred() {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return {promise, resolve};
}
function fixture({images = [], math = true, timeout = false} = {}) {
  const glyphs = deferred(), fonts = deferred(), events = [];
  const root = {
    querySelector: () => math,
    querySelectorAll: () => images,
    getBoundingClientRect: () => events.push('layout'),
    fonts: {ready: fonts.promise},
  };
  const context = vm.createContext({
    document: root, clearTimeout,
    setTimeout: timeout ? callback => setTimeout(callback, 0) : setTimeout,
    l: {loadMathJax: async () => events.push('load'), finishRenderMath: async () => {
      events.push('flush'); await glyphs.promise; events.push('flushed');
    }},
  });
  vm.runInContext(source, context);
  return {root, context, glyphs, fonts, events};
}
(async () => {
  const f = fixture(); let done = false;
  const pending = f.context.underlightPreparePdf(f.root).then(() => {done = true;});
  await new Promise(setImmediate);
  assert.deepEqual(f.events, ['load', 'flush']); assert.equal(done, false);
  f.glyphs.resolve(); await new Promise(setImmediate);
  assert.deepEqual(f.events, ['load', 'flush', 'flushed', 'layout']); assert.equal(done, false);
  f.fonts.resolve(); await pending; assert.equal(done, true);

  const img = new EventTarget(); Object.assign(img, {complete: false, naturalWidth: 0, src: 'diagram.png'});
  const i = fixture({math: false, images: [img]}); i.fonts.resolve();
  let loaded = false;
  const assetWait = i.context.underlightPreparePdf(i.root).then(() => {loaded = true;});
  await new Promise(setImmediate); assert.equal(loaded, false); assert.equal(img.loading, 'eager');
  img.naturalWidth = 100; img.dispatchEvent(new Event('load')); await assetWait;
  assert.equal(loaded, true); assert.deepEqual(i.events, ['layout']);

  const broken = fixture({math: false, images: [{complete: true, naturalWidth: 0, src: 'missing.png'}]});
  await assert.rejects(broken.context.underlightPreparePdf(broken.root), /PDF image failed to load/);
  const timed = fixture({math: false, timeout: true});
  await assert.rejects(timed.context.underlightPreparePdf(timed.root), /15 seconds/);
  console.log('Obsidian PDF readiness: math flush, fonts, images, failures and timeout passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
