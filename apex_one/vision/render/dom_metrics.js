(opts) => {
  const MM = 96 / 25.4;
  const LATIN = /[A-Za-z]/;
  const ARABIC = /[؀-ۿ]/;
  const transparent = (c) => !c || c === 'transparent' || /rgba\(.*,\s*0\)$/.test(c);
  const effectiveBg = (el) => {
    let e = el;
    while (e && e !== document.documentElement) {
      const c = getComputedStyle(e).backgroundColor;
      if (!transparent(c)) return c;
      e = e.parentElement;
    }
    return 'rgb(255, 255, 255)';
  };
  const unisolatedLatin = (el) => {
    const out = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const t = n.nodeValue;
      if (!LATIN.test(t)) continue;
      let p = n.parentElement, isolated = false;
      while (p && p !== el.parentElement) {
        if (p.tagName === 'BDI' || p.getAttribute('dir') === 'ltr') { isolated = true; break; }
        p = p.parentElement;
      }
      if (!isolated) out.push(t.trim().slice(0, 60));
    }
    return out;
  };
  const pages = [...document.querySelectorAll('section.page')];
  const result = {pages: [], fonts: [], viewport: {w: innerWidth, h: innerHeight}, htmlDir: document.documentElement.dir};
  try {
    document.fonts.forEach(f => { if (f.status === 'loaded') result.fonts.push(f.family.replace(/"/g, '') + ':' + f.weight); });
  } catch (e) {}
  for (const page of pages) {
    const pr = page.getBoundingClientRect();
    const body = page.querySelector('.page-body');
    const br = body ? body.getBoundingClientRect() : pr;
    const pcs = getComputedStyle(page);
    const items = [];
    for (const el of page.querySelectorAll('[data-block]')) {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      const range = document.createRange();
      range.selectNodeContents(el);
      const rects = [...range.getClientRects()].filter(x => x.width > 0.5 && x.height > 0.5);
      const lines = [];
      for (const x of rects) {
        const line = lines.find(l => Math.abs(l.top - x.top) < Math.max(4, x.height * 0.45));
        if (line) { line.left = Math.min(line.left, x.left); line.right = Math.max(line.right, x.right); }
        else lines.push({top: x.top, left: x.left, right: x.right});
      }
      lines.sort((a, b) => a.top - b.top);
      const widths = lines.map(l => l.right - l.left);
      const text = (el.innerText || '').replace(/\s+/g, ' ').trim();
      const clone = el.cloneNode(true);
      clone.querySelectorAll('.fact-free').forEach(x => x.remove());
      const diffText = (clone.textContent || '').replace(/\s+/g, ' ').trim();
      items.push({
        id: el.dataset.block, role: el.dataset.role, lang: el.getAttribute('lang') || 'ar',
        opinion: el.dataset.opinion === '1', humor: el.dataset.humor === '1',
        x: r.left - pr.left, y: r.top - pr.top, w: r.width, h: r.height,
        fontPx: parseFloat(cs.fontSize),
        maxFontPx: Math.max(parseFloat(cs.fontSize), ...[...el.querySelectorAll('*')]
          .filter(x => (x.textContent || '').trim().length > 0 && !x.closest('svg'))
          .map(x => parseFloat(getComputedStyle(x).fontSize) || 0)), fontFamily: cs.fontFamily, fontWeight: cs.fontWeight,
        lineHeightPx: parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.5,
        color: cs.color, bg: effectiveBg(el), dir: cs.direction, textAlign: cs.textAlign,
        letterSpacing: cs.letterSpacing, fontStyle: cs.fontStyle, textTransform: cs.textTransform,
        lines: lines.length, lineWidths: widths, chars: text.length, text: text.slice(0, 400), diffText: diffText.slice(0, 600),
        overflowX: el.scrollWidth - el.clientWidth, overflowY: el.scrollHeight - el.clientHeight,
        overflowStyle: cs.overflowX + '/' + cs.overflowY,
        radius: cs.borderTopLeftRadius, shadow: cs.boxShadow, bgImage: cs.backgroundImage,
        borders: [cs.borderTopWidth, cs.borderRightWidth, cs.borderBottomWidth, cs.borderLeftWidth].map(parseFloat),
        unisolatedLatin: ARABIC.test(text) ? unisolatedLatin(el) : [],
      });
    }
    const facts = [...page.querySelectorAll('[data-slot]')].map(f => {
      const r = f.getBoundingClientRect();
      return {slot: f.dataset.slot, claim: f.dataset.claim, hash: f.dataset.lockHash, display: f.dataset.display, cond: f.dataset.cond || null,
              text: (f.innerText || '').trim(), isolated: !!f.querySelector('bdi') || f.closest('bdi') !== null,
              visible: r.width > 0 && r.height > 0, y: r.top - pr.top, x: r.left - pr.left};
    });
    const colors = new Set();
    const cardLike = [];
    for (const el of page.querySelectorAll('*')) {
      if (el.closest('svg')) continue;
      const cs = getComputedStyle(el);
      if (!transparent(cs.color)) colors.add(cs.color);
      if (!transparent(cs.backgroundColor)) colors.add(cs.backgroundColor);
      const r = el.getBoundingClientRect();
      const bw = [cs.borderTopWidth, cs.borderRightWidth, cs.borderBottomWidth, cs.borderLeftWidth].map(parseFloat);
      const sides = bw.filter(w => w > 0).length;
      const hasBg = !transparent(cs.backgroundColor) && cs.backgroundColor !== pcs.backgroundColor;
      const area = r.width * r.height;
      if (el !== page && area > 900 && area < pr.width * pr.height * 0.5 &&
          ((hasBg && (sides >= 3 || parseFloat(cs.borderTopLeftRadius) > 0)) || (sides >= 4) || cs.boxShadow !== 'none')) {
        cardLike.push({tag: el.tagName, cls: el.className && el.className.baseVal === undefined ? el.className : '', w: r.width, h: r.height});
      }
    }
    // coverage by sampling (text blocks only)
    let covered = 0, total = 0;
    for (let gx = 0; gx < 40; gx++) for (let gy = 0; gy < 56; gy++) {
      const px = (gx + 0.5) / 40 * pr.width, py = (gy + 0.5) / 56 * pr.height;
      total++;
      if (items.some(i => px >= i.x && px <= i.x + i.w && py >= i.y && py <= i.y + i.h)) covered++;
    }
    const mixed = [];
    const tw = document.createTreeWalker(page, NodeFilter.SHOW_TEXT);
    let tn;
    while ((tn = tw.nextNode())) {
      if (!/\d+\s*[\/–-]\s*\d+/.test(tn.nodeValue)) continue;
      const pe = tn.parentElement;
      if (pe.closest('bdi,[dir=ltr]')) continue;
      if (getComputedStyle(pe).direction === 'rtl') mixed.push(tn.nodeValue.trim().slice(0, 40));
    }
    result.pages.push({
      unisolatedMixedDigits: mixed,
      pageId: page.dataset.pageId, nodeType: page.dataset.nodeType, archetype: page.dataset.archetype,
      firstFixation: page.dataset.firstFixation, w: pr.width, h: pr.height,
      body: {x: br.left - pr.left, y: br.top - pr.top, w: br.width, h: br.height,
             overflowY: body ? body.scrollHeight - body.clientHeight : 0, overflowX: body ? body.scrollWidth - body.clientWidth : 0},
      bg: pcs.backgroundColor, bgImage: pcs.backgroundImage, items, facts, colors: [...colors], cardLike,
      coverage: covered / total, hasLogo: !!page.querySelector('[data-brand=logo]'),
      hasFooter: !!page.querySelector('[data-brand=footer]'),
      footerRect: (() => { const f = page.querySelector('[data-brand=footer]'); if (!f) return null; const r = f.getBoundingClientRect(); return {y: r.top - pr.top, h: r.height}; })(),
      scrollW: document.documentElement.scrollWidth,
    });
  }
  return result;
}
