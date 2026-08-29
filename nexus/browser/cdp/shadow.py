_ACCESSIBLE_TEXT_JS = """
  const _GRIP_FORM_TAGS = new Set(['input', 'select', 'textarea']);
  const _GRIP_NO_VALUE_TYPES = new Set([
    'checkbox', 'radio', 'file', 'submit', 'button', 'reset', 'image', 'hidden',
    'password'
  ]);

  function gripLabelledByText(el) {
    const ids = (el.getAttribute('aria-labelledby') || '').trim();
    if (!ids) return '';
    const root = el.getRootNode();
    if (typeof root.getElementById !== 'function') return '';
    return ids.split(/\\s+/).map(function (id) {
      const ref = root.getElementById(id);
      return ref ? (ref.innerText || ref.textContent || '').trim() : '';
    }).filter(Boolean).join(' ');
  }

  function gripNativeLabelText(el) {
    if (!_GRIP_FORM_TAGS.has(el.tagName.toLowerCase())) return '';
    const labels = el.labels;
    if (!labels || !labels.length) return '';
    return Array.prototype.map.call(labels, function (l) {
      return (l.innerText || '').trim();
    }).filter(Boolean).join(' ');
  }

  function gripSvgTitleText(el) {
    if (typeof SVGElement === 'undefined' || !(el instanceof SVGElement)) return '';
    const t = el.querySelector && el.querySelector(':scope > title');
    return t ? (t.textContent || '').trim() : '';
  }

  function gripOwnText(el) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && _GRIP_NO_VALUE_TYPES.has(type)) {
      return (el.innerText || '').trim();
    }
    return (
      el.innerText || el.value || el.getAttribute('aria-label') ||
      gripSvgTitleText(el) || ''
    ).trim();
  }

  function gripCombine(label, own) {
    if (!own) return label;
    const l = label.toLowerCase(), o = own.toLowerCase();
    if (o.includes(l) || l.includes(o)) return own.length >= label.length ? own : label;
    return label + ': ' + own;
  }

  function gripSiblingText(el) {
    let n = el.previousSibling;
    while (n) {
      if (n.nodeType === 3 && n.textContent.trim()) return n.textContent.trim().slice(0, 60);
      if (n.nodeType === 1 && (n.innerText || '').trim()) return n.innerText.trim().slice(0, 60);
      n = n.previousSibling;
    }
    const parent = el.parentElement;
    if (parent) {
      for (const child of parent.childNodes) {
        if (child.nodeType === 3 && child.textContent.trim()) {
          return child.textContent.trim().slice(0, 60);
        }
      }
    }
    return '';
  }

  function gripHumanize(s) {
    return (s || '').replace(/[-_]+/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').trim();
  }

  const _GRIP_INFER_LABEL_TAGS = new Set(['input', 'textarea']);

  function gripInferredLabel(el) {
    const placeholder = (el.getAttribute('placeholder') || '').trim();
    if (placeholder) return placeholder;
    const title = (el.getAttribute('title') || '').trim();
    if (title) return title;
    const sibling = gripSiblingText(el);
    if (sibling) return sibling;
    return gripHumanize(el.getAttribute('name') || el.id || '');
  }

  function gripAccessibleText(el) {
    const own = gripOwnText(el);
    let label = gripLabelledByText(el) ||
      (el.getAttribute('aria-label') || '').trim() ||
      gripNativeLabelText(el);
    if (!label && _GRIP_INFER_LABEL_TAGS.has(el.tagName.toLowerCase())) {
      label = gripInferredLabel(el);
    }
    if (!label) return own;
    if (el.tagName.toLowerCase() === 'select') return label;
    return gripCombine(label, own);
  }
"""

_COLLECT_CANDIDATES_JS = _ACCESSIBLE_TEXT_JS + """
  const INTERACTIVE_TAGS = new Set([
    'a','button','input','select','textarea','details','summary','canvas'
  ]);
  const INTERACTIVE_ROLES = new Set([
    'button','link','checkbox','radio','menuitem','tab','textbox',
    'combobox','listbox','option','switch','treeitem','slider'
  ]);
  const _TRACKING_HOSTS = [
    'googletagmanager.com', 'google-analytics.com', 'facebook.net',
    'hotjar.com', 'sentry.io', 'recaptcha.net', 'doubleclick.net',
    'analytics.google.com', 'pixel.facebook.com', 'tr.snapchat.com'
  ];

  function gripRole(el) {
    return el.getAttribute('role') || el.getAttribute('aria-role') || '';
  }

  function gripIsSvgCandidate(el) {
    if (typeof SVGElement === 'undefined' || !(el instanceof SVGElement)) return false;
    if (el.hasAttribute('aria-label')) return true;
    return !!(el.querySelector && el.querySelector(':scope > title'));
  }

  function gripIsCandidate(el, tag, role) {
    return INTERACTIVE_TAGS.has(tag) || INTERACTIVE_ROLES.has(role) || gripIsSvgCandidate(el);
  }

  function gripIsHidden(el) {
    if (typeof el.checkVisibility === 'function') {
      if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return true;
    } else {
      const s = window.getComputedStyle(el);
      if (s.display === 'none' || s.visibility === 'hidden' ||
          parseFloat(s.opacity) === 0) return true;
    }
    if (el.getAttribute('aria-hidden') === 'true') return true;
    if (el.offsetWidth === 0 || el.offsetHeight === 0) return true;

    const style = window.getComputedStyle(el);
    if (parseFloat(style.textIndent) < -500) return true;
    if (parseFloat(style.fontSize) === 0) return true;
    if (style.color === 'rgba(0, 0, 0, 0)' &&
        style.getPropertyValue('-webkit-background-clip') !== 'text' &&
        style.backgroundClip !== 'text') return true;

    const r = el.getBoundingClientRect();
    if (r.right + window.scrollX <= 0 || r.bottom + window.scrollY <= 0) return true;

    return false;
  }

  function gripComboboxInfo(el, role) {
    const hasPopup = el.hasAttribute('aria-haspopup');
    const hasExpanded = el.hasAttribute('aria-expanded');
    if (role !== 'combobox' && role !== 'listbox' && !hasPopup && !hasExpanded) return null;
    const expanded = el.getAttribute('aria-expanded') === 'true';
    const ownedId = (el.getAttribute('aria-controls') || el.getAttribute('aria-owns') || '')
      .trim().split(/\\s+/)[0];
    const optionsRoot = ownedId ? document.getElementById(ownedId) : null;
    let options = null;
    if (optionsRoot) {
      options = Array.prototype.slice
        .call(optionsRoot.querySelectorAll('[role="option"], option'))
        .slice(0, 50)
        .map(function (o) { return (o.innerText || o.textContent || '').trim().slice(0, 80); })
        .filter(Boolean);
    }
    return { expanded: expanded, options: options };
  }

  function gripCollect() {
    const out = [];
    function walk(root, inShadow) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null);
      let node = walker.currentNode;
      while (node) {
        const el = node;
        if (!el.tagName) { node = walker.nextNode(); continue; }
        const tag = el.tagName.toLowerCase();
        if (tag === 'iframe') {
          const src = el.getAttribute('src') || el.getAttribute('data-src') || '';
          let host = '';
          try { host = new URL(src, location.href).hostname; } catch (e) {}
          if (_TRACKING_HOSTS.some(p => host.includes(p))) {
            node = walker.nextNode();
            continue;
          }
          out.push({ el: el, tag: tag, role: 'iframe', inShadow: inShadow, isIframe: true });
          node = walker.nextNode();
          continue;
        }
        const role = gripRole(el);
        let addedAsCandidate = false;
        if (gripIsCandidate(el, tag, role) && !gripIsHidden(el)) {
          out.push({
            el: el, tag: tag, role: role, inShadow: inShadow,
            combobox: gripComboboxInfo(el, role),
          });
          addedAsCandidate = true;
        }
        if (el.shadowRoot) {
          walk(el.shadowRoot, true);
        } else if (window.__gripClosedRoots && window.__gripClosedRoots.has(el)) {
          try {
            walk(window.__gripClosedRoots.get(el), true);
          } catch (e) {
            if (!addedAsCandidate) {
              out.push({
                el: el, tag: tag, role: role, inShadow: inShadow,
                closedShadowUnreadable: true,
              });
            }
          }
        }
        node = walker.nextNode();
      }
    }
    walk(document.body, false);
    return out;
  }

  function gripElementState(el) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const disabled = el.disabled === true || el.getAttribute('aria-disabled') === 'true';
    const required = el.required === true || el.getAttribute('aria-required') === 'true';

    let checked = null;
    if (tag === 'input' && (type === 'checkbox' || type === 'radio')) {
      checked = !!el.checked;
    } else if (['checkbox', 'switch'].includes(el.getAttribute('role') || '')) {
      checked = el.getAttribute('aria-checked') === 'true';
    }

    let selected = null;
    if (tag === 'option') {
      selected = !!el.selected;
    } else if (el.hasAttribute('aria-selected')) {
      selected = el.getAttribute('aria-selected') === 'true';
    }

    let value = null;
    if ((tag === 'input' || tag === 'textarea') && !_GRIP_NO_VALUE_TYPES.has(type)) {
      value = (el.value || '').slice(0, 80) || null;
    } else if (tag === 'select') {
      const opt = el.options && el.options[el.selectedIndex];
      value = opt ? (opt.text || opt.value || '').slice(0, 80) || null : null;
    }

    return { disabled: disabled, required: required, checked: checked,
             selected: selected, value: value };
  }

  function gripIframeSummary(el) {
    const parts = [];
    const src = el.getAttribute('src') || el.getAttribute('data-src') || '';
    if (src) parts.push('src=' + src);
    const title = el.getAttribute('title') || '';
    if (title) parts.push('title=' + title);
    const name = el.getAttribute('name') || '';
    if (name) parts.push('name=' + name);
    return parts.join(' ');
  }

  function gripStamp(el) {
    const seen = (window.__gripStamped = window.__gripStamped || new WeakSet());
    const h = el.getAttribute('data-grip-h');
    if (h && seen.has(el)) return h;
    window.__gripHandleSeq = (window.__gripHandleSeq || 0) + 1;
    const fresh = 'h' + window.__gripHandleSeq;
    el.setAttribute('data-grip-h', fresh);
    seen.add(el);
    return fresh;
  }
"""

_PROBE_CANDIDATES_JS = _COLLECT_CANDIDATES_JS + """
  const PRE_RANK_LIMIT = __GRIP_PRE_RANK_LIMIT__;
  const MAX_LISTENER_PROBE_NODES = __GRIP_MAX_LISTENER_PROBE_NODES__;

  const _PROBE_DENY_TAGS = new Set([
    'html','head','body','script','style','template','noscript','meta','link',
    'title','p','pre','blockquote','code','b','i','strong','em','small','sup',
    'sub','br','hr','option','style'
  ]);

  function gripHasOwnText(el) {
    for (const n of el.childNodes) {
      if (n.nodeType === 3 && n.textContent && n.textContent.trim().length > 0) return true;
    }
    return false;
  }

  function gripCheapScore(el) {
    let s = 0;
    if (el.hasAttribute('onclick')) s += 3;
    if (el.tabIndex >= 0) s += 2;
    for (const a of el.attributes) { if (a.name.startsWith('data-')) { s += 2; break; } }
    if ((el.className || '').length > 0) s += 1;
    const ownLen = (el.textContent || '').trim().length;
    if (ownLen > 0 && ownLen <= 60) s += 1;
    return s;
  }

  function gripCollectProbeCandidates() {
    const shortlist = [];
    function walk(root, inShadow) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null);
      let node = walker.currentNode;
      while (node) {
        const el = node;
        if (el.tagName) {
          const tag = el.tagName.toLowerCase();
          if (!_PROBE_DENY_TAGS.has(tag)) {
            const role = gripRole(el);
            if (!gripIsCandidate(el, tag, role) && gripHasOwnText(el)) {
              shortlist.push({ el: el, tag: tag, role: role, inShadow: inShadow,
                                score: gripCheapScore(el) });
            }
          }
          if (el.shadowRoot) walk(el.shadowRoot, true);
        }
        node = walker.nextNode();
      }
    }
    walk(document.body, false);

    shortlist.sort(function (a, b) { return b.score - a.score; });
    const ranked = shortlist.slice(0, PRE_RANK_LIMIT);

    const out = [];
    for (const c of ranked) {
      const el = c.el;
      if (gripIsHidden(el)) continue;
      const style = window.getComputedStyle(el);
      let score = c.score;
      if (style.cursor === 'pointer') score += 2;
      out.push({ el: el, tag: c.tag, role: c.role, inShadow: c.inShadow, score: score });
    }
    out.sort(function (a, b) { return b.score - a.score; });
    return out.slice(0, MAX_LISTENER_PROBE_NODES).map(function (c) {
      const el = c.el;
      const rect = el.getBoundingClientRect();
      return {
        handle: gripStamp(el),
        tag: c.tag,
        role: c.role || c.tag,
        text: gripAccessibleText(el).slice(0, 120),
        inShadowDom: c.inShadow,
        cx: Math.round(rect.left + rect.width / 2),
        cy: Math.round(rect.top + rect.height / 2)
      };
    });
  }
"""

GRIP_PRE_RANK_LIMIT = 150
GRIP_MAX_LISTENER_PROBE_NODES = 40

_PROBE_CANDIDATES_JS = (
    _PROBE_CANDIDATES_JS
    .replace("__GRIP_PRE_RANK_LIMIT__", str(GRIP_PRE_RANK_LIMIT))
    .replace("__GRIP_MAX_LISTENER_PROBE_NODES__", str(GRIP_MAX_LISTENER_PROBE_NODES))
)

PROBE_CLICKABLE_JS = """
(function() {
""" + _PROBE_CANDIDATES_JS + """
  return JSON.stringify(gripCollectProbeCandidates());
})();
"""


DISCOVER_ELEMENTS_JS = """
(function() {
""" + _COLLECT_CANDIDATES_JS + """
  return JSON.stringify(gripCollect().map(function (c, i) {
    const el = c.el;
    const rect = el.getBoundingClientRect();
    const state = gripElementState(el);
    return {
      index: i,
      handle: gripStamp(el),
      tag: c.tag,
      role: c.role || c.tag,
      text: c.isIframe ? gripIframeSummary(el) : gripAccessibleText(el).slice(0, 120),
      placeholder: el.getAttribute('placeholder') || null,
      href: (function () {
        if (c.tag !== 'a') return null;
        const raw = el.getAttribute('href');
        if (!raw || raw.startsWith('#')) return null;
        const abs = el.href;
        return /^https?:/i.test(abs) ? abs : null;
      })(),
      inShadowDom: c.inShadow,
      cx: Math.round(rect.left + rect.width / 2),
      cy: Math.round(rect.top + rect.height / 2),
      canvasWidth: c.tag === 'canvas' ? Math.round(rect.width) : null,
      canvasHeight: c.tag === 'canvas' ? Math.round(rect.height) : null,
      isCombobox: !!c.combobox,
      comboboxExpanded: c.combobox ? c.combobox.expanded : null,
      comboboxOptions: c.combobox ? c.combobox.options : null,
      closedShadowUnreadable: !!c.closedShadowUnreadable,
      disabled: state.disabled,
      required: state.required,
      checked: state.checked,
      selected: state.selected,
      value: state.value
    };
  }));
})();
"""


CLOSED_SHADOW_PATCH_JS = """
(function () {
  if (window.__gripClosedRoots) return;
  window.__gripClosedRoots = new WeakMap();
  const nativeAttachShadow = Element.prototype.attachShadow;
  Element.prototype.attachShadow = function (init) {
    const root = nativeAttachShadow.call(this, init);
    if (init && init.mode === 'closed') {
      window.__gripClosedRoots.set(this, root);
    }
    return root;
  };
})();
"""


_RESOLVE_JS = _ACCESSIBLE_TEXT_JS + """
  function gripQuery(root, handle) {
    const sel = '[data-grip-h="' + CSS.escape(handle) + '"]';
    const hit = root.querySelector(sel);
    if (hit) return hit;
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) {
        const deep = gripQuery(el.shadowRoot, handle);
        if (deep) return deep;
      }
    }
    return null;
  }

  function gripResolve(handle, expectedTag, expectedText) {
    const el = gripQuery(document, handle);
    if (!el) return { el: null, reason: 'not_found' };
    const tag = el.tagName.toLowerCase();
    if (expectedTag && tag !== expectedTag) return { el: null, reason: 'identity_mismatch' };
    if (expectedText) {
      const actual = gripAccessibleText(el).slice(0, 120);
      if (actual !== expectedText) return { el: null, reason: 'identity_mismatch' };
    }
    return { el: el, reason: '' };
  }
"""

CLICK_ELEMENT_JS = """
function(handle, expectedTag, expectedText) {
""" + _RESOLVE_JS + """
  const r = gripResolve(handle, expectedTag, expectedText);
  if (!r.el) return { ok: false, reason: r.reason };
  const el = r.el;

  if (el.disabled === true || el.getAttribute('aria-disabled') === 'true') {
    return { ok: false, reason: 'disabled' };
  }

  let rect = el.getBoundingClientRect();
  const offscreen = rect.width === 0 || rect.height === 0 ||
    rect.bottom <= 0 || rect.right <= 0 ||
    rect.top >= window.innerHeight || rect.left >= window.innerWidth;
  if (offscreen) {
    el.scrollIntoView({ block: 'center', inline: 'center' });
    rect = el.getBoundingClientRect();
  }

  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const hitRoot = el.getRootNode();
  const hitFn = (hitRoot && typeof hitRoot.elementFromPoint === 'function')
    ? hitRoot.elementFromPoint.bind(hitRoot)
    : document.elementFromPoint.bind(document);
  const hit = hitFn(cx, cy);
  if (hit && !(el.contains(hit) || hit.contains(el))) {
    const cls = hit.getAttribute('class');
    return {
      ok: false, reason: 'obscured',
      occluder: hit.tagName.toLowerCase() + (cls ? '.' + cls.trim().split(/\\s+/).join('.') : '')
    };
  }

  el.click();
  return { ok: true, reason: '' };
}
"""


TYPE_ELEMENT_JS = """
function(handle, text, expectedTag, expectedText) {
""" + _RESOLVE_JS + """
  const r = gripResolve(handle, expectedTag, expectedText);
  if (!r.el) return { ok: false, reason: r.reason };
  const el = r.el;
  const tag = el.tagName.toLowerCase();
  if (!(tag === 'input' || tag === 'textarea' || el.isContentEditable)) {
    return { ok: false, reason: 'not_typable' };
  }
  el.focus();

  if (el.isContentEditable) {
    el.textContent = '';
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.textContent = text;
    el.dispatchEvent(new Event('input', { bubbles: true }));
  } else {
    const proto = tag === 'textarea'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    function setValue(v) {
      if (nativeSetter) { nativeSetter.call(el, v); } else { el.value = v; }
    }
    setValue('');
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
    setValue(text);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
  }
  el.dispatchEvent(new Event('change', { bubbles: true }));

  const actual = el.isContentEditable ? (el.textContent || '') : el.value;
  if (actual !== text) {
    return { ok: false, reason: 'value_mismatch:' + String(actual).slice(0, 80) };
  }
  return { ok: true, reason: '' };
}
"""


PAGE_TEXT_JS = """
(function() {
  const main = document.querySelector('main, [role="main"]') || document.body;
  return (main.innerText || main.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 8000);
})();
"""


CLICK_REVEAL_JS = """
(function () {
  const PHRASES = ['show more', 'load more', 'next', 'expand', 'read more', 'see more'];

  function visible(el) {
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  }
  function textMatches(el) {
    const t = (el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase();
    return PHRASES.some(function (p) { return t.includes(p); });
  }
  function staysOnPage(el) {
    if (el.tagName.toLowerCase() !== 'a') return true;
    const href = el.getAttribute('href');
    if (!href || href.charAt(0) === '#') return true;
    let abs;
    try { abs = new URL(href, location.href); } catch (e) { return false; }
    return abs.origin === location.origin
      && abs.pathname === location.pathname
      && abs.search === location.search;
  }

  let target = null;
  for (const el of document.querySelectorAll('a, button, [role="button"]')) {
    if (visible(el) && textMatches(el) && staysOnPage(el)) { target = el; break; }
  }
  if (!target) {
    for (const el of document.querySelectorAll('[aria-expanded="false"]')) {
      if (visible(el)) { target = el; break; }
    }
  }
  if (!target) return false;
  target.click();
  return true;
})();
"""

SCROLL_BOTTOM_JS = """
(function () {
  function isScrollable(el) {
    if (!el || el === document.documentElement || el === document.body) return false;
    if (el.scrollHeight - el.clientHeight < 40) return false;
    const style = window.getComputedStyle(el);
    return /(auto|scroll)/.test(style.overflowY);
  }

  let target = null;
  let bestArea = 0;
  for (const el of document.querySelectorAll('*')) {
    if (!isScrollable(el)) continue;
    const r = el.getBoundingClientRect();
    const area = r.width * r.height;
    if (area > bestArea) { bestArea = area; target = el; }
  }

  if (target) {
    target.scrollTop = Math.min(target.scrollTop + target.clientHeight, target.scrollHeight);
  } else {
    window.scrollTo(0, document.body.scrollHeight);
  }
  return true;
})();
"""


READ_CONTENT_JS = r"""
(function () {
  const BAD_WORDS = [
    'nav', 'menu', 'sidebar', 'footer', 'header', 'banner', 'cookie', 'consent',
    'promo', 'advert', 'subscribe', 'newsletter', 'related', 'comment', 'share',
    'social', 'breadcrumb',
  ];
  const BAD = new RegExp('(^|[-_ ])(' + BAD_WORDS.join('|') + ')([-_ ]|$)', 'i');
  const CHROME_TAGS = ['nav','footer','header','aside','script','style','noscript','form'];
  const CHROME_ROLES = ['navigation','banner','contentinfo','complementary','search'];

  function isChrome(el) {
    if (!el || !el.tagName) return false;
    if (CHROME_TAGS.includes(el.tagName.toLowerCase())) return true;
    if (CHROME_ROLES.includes(el.getAttribute('role') || '')) return true;
    return BAD.test(el.className || '') || BAD.test(el.id || '');
  }

  function score(el) {
    let n = 0;
    for (const p of el.querySelectorAll('p, li, pre, blockquote')) {
      if (isChrome(p) || isChrome(p.parentElement)) continue;
      n += (p.innerText || '').trim().length;
    }
    return n;
  }

  let best = document.querySelector('article, main, [role="main"]');
  if (!best) {
    let bestScore = 0;
    for (const el of document.querySelectorAll('div, section, article, main')) {
      const s = score(el);
      if (s > bestScore * 1.05) { bestScore = s; best = el; }
    }
  }
  best = best || document.body;

  const blocks = [];
  const trail = [];
  const walker = document.createTreeWalker(best, NodeFilter.SHOW_ELEMENT);
  let node = walker.currentNode;
  while (node) {
    const tag = node.tagName.toLowerCase();
    if (isChrome(node)) {
      let next = walker.nextSibling();
      while (!next && walker.parentNode()) next = walker.nextSibling();
      node = next;
      continue;
    }
    if (/^h[1-6]$/.test(tag)) {
      const level = +tag[1];
      const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
      if (text) {
        while (trail.length && trail[trail.length - 1].level >= level) trail.pop();
        trail.push({ level: level, text: text });
        blocks.push({ kind: 'heading', level: level, text: text,
                      path: trail.map(function (t) { return t.text; }) });
      }
    } else if (['p','li','pre','blockquote','td'].includes(tag)) {
      if (!node.querySelector('p, li, pre, blockquote')) {
        const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
        if (text.length > 2) {
          blocks.push({ kind: tag === 'pre' ? 'code' : 'text', level: 0, text: text,
                        path: trail.map(function (t) { return t.text; }) });
        }
      }
    }
    node = walker.nextNode();
  }
  return JSON.stringify({ title: document.title, url: location.href, blocks: blocks });
})();
"""
