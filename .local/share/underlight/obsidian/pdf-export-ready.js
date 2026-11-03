// Underlight PDF readiness guard for Better Export PDF 2.0.3.
// Keep this function self-contained: engine 1 runs it in its print webview.
async function underlightWaitForPdfAssets(root = document) {
  const doc = root.ownerDocument || root;
  const cleanups = [];
  let timer;
  try {
    const images = [...root.querySelectorAll('img')].map(img => {
      img.loading = 'eager';
      if (img.complete) {
        if (!img.naturalWidth) throw new Error('PDF image failed to load: ' + img.src);
        return Promise.resolve();
      }
      return new Promise((resolve, reject) => {
        const loaded = () => img.naturalWidth ? resolve() : failed();
        const failed = () => reject(new Error('PDF image failed to load: ' + img.src));
        img.addEventListener('load', loaded);
        img.addEventListener('error', failed);
        cleanups.push(() => {
          img.removeEventListener('load', loaded);
          img.removeEventListener('error', failed);
        });
      });
    });
    // Trigger layout before waiting for fonts used by the rendered equations.
    (doc.body || root).getBoundingClientRect();
    await Promise.race([
      Promise.all([...images, doc.fonts.ready]),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('PDF assets did not finish loading within 15 seconds')), 15000);
      }),
    ]);
  } finally {
    clearTimeout(timer);
    cleanups.forEach(cleanup => cleanup());
  }
}

async function underlightPreparePdf(root) {
  if (root.querySelector('mjx-container, .math')) {
    await l.loadMathJax();
    // tex2chtml is synchronous, but Obsidian batches the glyph stylesheet update.
    await l.finishRenderMath();
  }
  await underlightWaitForPdfAssets(root);
}
