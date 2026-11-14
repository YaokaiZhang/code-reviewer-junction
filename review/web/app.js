/* Earned Trust — owner view. No build step; data comes from data.js (window.DOSSIERS). */
(function () {
  'use strict';

  var TIERS = ['Proved', 'Tested', 'Measured', 'Argued', 'Refused'];
  var MACHINE = { Proved: 1, Tested: 1, Measured: 1 };
  var GLYPH = { Proved: '■', Tested: '▲', Measured: '●', Argued: '◆', Refused: '✕' };
  var PICKS = [
    { v: 'accept', k: 'A', cls: 'accept' },
    { v: 'reject', k: 'R', cls: 'reject' },
    { v: 'send back', k: 'S', cls: 'send-back' }
  ];
  var DATA = window.DOSSIERS || {};
  var app = document.getElementById('app');
  var mastRight = document.getElementById('mast-right');
  var state = { key: null, picks: {}, receipt: null, justSigned: false };
  var clockTimer = null;

  /* ---------- helpers ---------- */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function lc(t) { return String(t || '').toLowerCase(); }
  function store(k, v) {
    try { if (v === undefined) return JSON.parse(localStorage.getItem(k)); localStorage.setItem(k, JSON.stringify(v)); }
    catch (e) { return null; }
  }
  function claims(d) { return Array.isArray(d.claims) ? d.claims : []; }
  function humanOf(d) {
    return claims(d).filter(function (c) { return !MACHINE[c.tier]; }).sort(function (a, b) {
      return (a.tier === 'Refused' ? 0 : 1) - (b.tier === 'Refused' ? 0 : 1) || String(a.id).localeCompare(String(b.id));
    });
  }
  function machineOf(d) {
    return claims(d).filter(function (c) { return MACHINE[c.tier]; }).sort(function (a, b) {
      return TIERS.indexOf(a.tier) - TIERS.indexOf(b.tier) || String(a.id).localeCompare(String(b.id));
    });
  }
  function counts(d) {
    var n = {}; TIERS.forEach(function (t) { n[t] = 0; });
    claims(d).forEach(function (c) { if (n[c.tier] != null) n[c.tier]++; });
    return n;
  }
  function keys() {
    return Object.keys(DATA).sort(function (a, b) {
      var sa = DATA[a].sample ? 1 : 0, sb = DATA[b].sample ? 1 : 0;
      return sa - sb || a.localeCompare(b);
    });
  }
  function stamp(d) {
    var M = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
    function p(n) { return String(n).padStart(2, '0'); }
    return p(d.getDate()) + '-' + M[d.getMonth()] + '-' + d.getFullYear() + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }
  function strip(d) {
    var cs = claims(d).slice().sort(function (a, b) { return TIERS.indexOf(a.tier) - TIERS.indexOf(b.tier); });
    return '<span class="strip" aria-hidden="true">' + cs.map(function (c) {
      return '<i class="c-' + lc(c.tier) + (MACHINE[c.tier] ? '' : ' human') + '" style="--c:var(--t-' + lc(c.tier) + ')"></i>';
    }).join('') + '</span>';
  }

  /* ---------- landing ---------- */
  function renderLanding() {
    mastRight.innerHTML = '';
    var ks = keys();
    var items = ks.map(function (k) {
      var d = DATA[k], h = humanOf(d), r = d._receipt;
      var st = r ? '<span class="state-signed">SIGNED</span>'
        : h.length ? '<span style="color:var(--t-argued)">' + h.length + ' OPEN</span>'
        : '<span class="dim">SETTLED</span>';
      var n = counts(d), lbl = TIERS.filter(function (t) { return n[t]; }).map(function (t) { return n[t] + ' ' + t; }).join(', ');
      return '<li><a href="#/d/' + encodeURIComponent(k) + '" aria-label="' + esc(d.branch + ': ' + (d.title || '') + '. ' + lbl + (r ? '. Signed.' : '')) + '">' +
        '<span class="arrow" aria-hidden="true">▸</span>' +
        '<span class="bname">' + esc(d.branch || k) + (d.sample ? ' <span class="dim">· sample</span>' : '') + '</span>' +
        '<span class="bstate">' + st + '</span>' +
        '<span class="bt">' + esc(d.title || '') + '</span>' +
        strip(d) +
        '<span class="gc" aria-hidden="true">' + TIERS.map(function (t) {
          return '<span class="c-' + lc(t) + (n[t] ? '' : ' z') + '">' + GLYPH[t] + n[t] + '</span>';
        }).join('') + '</span></a></li>';
    }).join('') || '<li class="empty dim">NO DOSSIERS — run render_web.py</li>';

    var caps = TIERS.map(function (t, i) {
      return (i === 3 ? '<span class="gap"></span>' : '') +
        '<div class="cap ' + lc(t) + '"><b aria-hidden="true">' + GLYPH[t] + '</b><i>' + t + '</i></div>';
    }).join('');

    app.innerHTML =
      '<section class="landing">' +
        '<div class="hero">' +
          '<h1><span>Read the evidence,</span><em>not the diff.</em></h1>' +
          '<div class="ladder">' + caps +
            '<span class="bracket machine">machine</span><span class="bracket owner">owner</span>' +
          '</div>' +
        '</div>' +
        '<div class="stage">' +
          '<div class="scene">' +
            '<div class="face back"></div><div class="face left"></div><div class="face right"></div><div class="face top"></div><div class="face bottom"></div>' +
            '<div class="face front">' +
              '<div class="inset"><div class="crt">' +
                '<div class="flicker"></div><div class="sweep"></div>' +
                '<div class="term">' +
                  '<div class="term-head"><span class="inv">DOSSIERS</span><span class="dim" id="clock"></span></div>' +
                  '<ul class="blist">' + items + '</ul>' +
                  '<div class="prompt" style="margin-top:auto">&gt; <span class="cursor"></span></div>' +
                '</div>' +
              '</div></div>' +
              '<div class="foot"><span class="badge"></span><span class="led on"></span>' +
                '<span class="grill"><span></span><span></span><span></span><span></span><span></span></span>' +
                '<span class="slot"></span></div>' +
              '<div class="sticker st-ball" style="left:178px;bottom:20px"></div>' +
              '<div class="sticker st-star" style="left:236px;bottom:16px" aria-hidden="true">★</div>' +
              '<div class="sticker st-text" style="left:304px;bottom:30px">EARNED<br>TRUST</div>' +
            '</div>' +
            '<div class="kbd" aria-hidden="true">' + kbdKeys() + '</div>' +
          '</div>' +
        '</div>' +
      '</section>';
    tickClock();
  }
  function kbdKeys() {
    var s = '';
    for (var i = 0; i < 14; i++) s += '<span></span>';
    s += '<span class="w2"></span>'; for (i = 0; i < 11; i++) s += '<span></span>'; s += '<span></span>';
    s += '<span class="w2"></span><span></span><span></span><span class="sp"></span><span></span><span></span><span class="w2"></span>';
    return s;
  }
  function tickClock() {
    clearInterval(clockTimer);
    var el = document.getElementById('clock');
    if (!el) return;
    var f = function () { el.textContent = stamp(new Date()); };
    f(); clockTimer = setInterval(f, 1000);
  }

  /* ---------- dossier ---------- */
  function evidenceBlock(d, c) {
    var out = '';
    var chain = Array.isArray(c.chain) ? c.chain : [];
    if (chain.length) {
      out += '<div class="chain">' + chain.map(function (l, i) {
        return '<span class="lk c-' + lc(l.tier) + '">' + (GLYPH[l.tier] || '·') + ' ' + esc(l.tier) + '<span>' + esc(l.link) + '</span></span>';
      }).join('') + '</div>';
    }
    (c.evidence || []).forEach(function (ref) {
      var ev = (d._evidence || {})[ref];
      var name = String(ref).split('/').pop().replace(/\.json$/, '');
      var res = ev ? lc(ev.result) || 'missing' : 'missing';
      out += '<div class="evl"><span class="res ' + esc(res) + '">' + esc(ev ? String(ev.result || '?').toUpperCase() : 'MISSING') + '</span>' +
        '<a href="../' + esc(ref) + '" target="_blank" rel="noopener">' + esc(name) + '</a>' +
        '<span class="evs">' + (ev ? esc(ev.summary || '') + (ev.produced_by === 'hand' ? '<span class="hand">[hand]</span>' : '') : '') + '</span>' +
        (ev && ev.command ? '<span class="cmd">' + esc(ev.command) + '</span>' : '') +
        '</div>';
    });
    if ((c.diff_parts || []).length) {
      out += '<div class="dp">' + c.diff_parts.map(function (p) { return '<code>' + esc(p) + '</code>'; }).join('') + '</div>';
    }
    if (c.requirement) {
      out += '<div class="req">' + esc(c.requirement) + (c.requirement_inferred ? ' <span class="inf">inferred</span>' : '') + '</div>';
    }
    return out ? '<div class="ev">' + out + '</div>' : '';
  }

  function ownerRow(d, c) {
    var pick = state.picks[c.id];
    var name = 'pick-' + c.id;
    return '<article class="own c-' + lc(c.tier) + (pick ? ' picked' : '') + '" id="row-' + esc(c.id) + '" data-id="' + esc(c.id) + '" tabindex="-1">' +
      '<div class="own-h"><span class="tg">' + GLYPH[c.tier] + ' ' + esc(c.tier.toUpperCase()) + '</span><span class="id">' + esc(c.id) + '</span>' +
        (c.owner_role ? '<span class="role">' + esc(c.owner_role) + '</span>' : '') + '</div>' +
      '<p class="claim-t">' + esc(c.claim) + '</p>' +
      (c.why_this_tier ? '<p class="why">' + esc(c.why_this_tier) + '</p>' : '') +
      evidenceBlock(d, c) +
      '<fieldset class="keys"><legend>' + esc(c.id) + '</legend>' +
        PICKS.map(function (p) {
          var id = name + '-' + p.cls;
          return '<span class="key ' + p.cls + '"><input type="radio" name="' + esc(name) + '" id="' + esc(id) + '" value="' + p.v + '"' + (pick === p.v ? ' checked' : '') + ' data-claim="' + esc(c.id) + '">' +
            '<label for="' + esc(id) + '"><kbd aria-hidden="true">' + p.k + '</kbd>' + p.v + '</label></span>';
        }).join('') +
      '</fieldset>' +
    '</article>';
  }

  function machineRow(d, c) {
    return '<details class="mach c-' + lc(c.tier) + '" id="row-' + esc(c.id) + '">' +
      '<summary><span class="g" aria-hidden="true">' + GLYPH[c.tier] + '</span><span class="tn">' + esc(c.tier) + '</span><span class="id">' + esc(c.id) + '</span>' +
      '<span class="ct">' + esc(c.claim) + '</span><span class="tw" aria-hidden="true">▸</span></summary>' +
      '<div class="body">' + (c.why_this_tier ? '<p class="why">' + esc(c.why_this_tier) + '</p>' : '') + evidenceBlock(d, c) + '</div>' +
    '</details>';
  }

  function list(title, items, fmt, hot) {
    items = Array.isArray(items) ? items : [];
    return '<section class="lst' + (hot && items.length ? ' hot' : '') + '"><h4><span class="inv">' + title + '</span><span class="k">' + items.length + '</span></h4><ul>' +
      (items.length ? items.map(function (x) { return '<li>' + fmt(x) + '</li>'; }).join('') : '<li class="none"></li>') + '</ul></section>';
  }

  function renderDossier(key) {
    var d = DATA[key];
    if (!d) {
      app.innerHTML = '<p class="notfound">No dossier “' + esc(key) + '”. <a href="#/">Back</a></p>';
      return;
    }
    state.key = key;
    state.picks = store('et:picks:' + key) || {};
    state.receipt = d._receipt || null;
    state.justSigned = false;
    if (state.receipt && !Object.keys(state.picks).length) {
      (state.receipt.picks || []).forEach(function (p) { state.picks[p.id] = p.pick; });
    }
    mastRight.innerHTML = '<a href="#/" style="text-decoration:none">↩ dossiers</a>';

    var n = counts(d), total = claims(d).length || 1;
    var human = humanOf(d), machine = machineOf(d);
    var diff = d.diff || {};
    var issueNo = d.issue != null ? '<em>#</em>' + esc(d.issue) : esc(d.branch);

    var tiers = TIERS.map(function (t, i) {
      var owner = !MACHINE[t];
      return (i === 3 ? '<span class="sep" aria-hidden="true"></span>' : '') +
        '<button type="button" class="tier c-' + lc(t) + (owner ? ' owner' : '') + '" data-jump="' + t + '"' + (n[t] ? '' : ' disabled') + ' aria-label="' + n[t] + ' ' + t + '">' +
          '<span class="n' + (n[t] ? '' : ' zero') + '">' + n[t] + '</span>' +
          '<span class="nm"><span aria-hidden="true">' + GLYPH[t] + '</span> ' + t + '</span>' +
          '<span class="bar"><b style="--p:' + (100 * n[t] / total).toFixed(1) + '%"></b></span>' +
        '</button>';
    }).join('');

    var leds = human.map(function (c) { return '<span class="led" data-led="' + esc(c.id) + '"></span>'; }).join('');

    app.innerHTML =
      '<section class="dossier">' +
        '<aside class="side">' +
          '<div class="issue-no">' + issueNo + '</div>' +
          '<h1 class="issue-title">' + esc(d.title || d.branch) + '</h1>' +
          '<dl class="meta">' +
            '<dt>branch</dt><dd>' + esc(d.branch) + '</dd>' +
            '<dt>head</dt><dd>' + esc(d.base || '?') + ' → ' + esc(d.head || '?') + '</dd>' +
            (diff.files != null ? '<dt>diff</dt><dd>' + esc(diff.files) + ' files <span class="add">+' + esc(diff.insertions) + '</span> <span class="del">−' + esc(diff.deletions) + '</span></dd>' : '') +
          '</dl>' +
          '<div class="printer-zone" id="pzone">' +
            '<div class="feed" id="feed"></div>' +
            '<form class="printer" id="printer" autocomplete="off">' +
              '<span class="stub" id="stub" aria-hidden="true"></span>' +
              '<div class="p-top"><div class="p-leds" aria-hidden="true">' + leds + '</div><div id="slip-tools"></div></div>' +
              '<div class="p-row">' +
                '<label class="sr" for="signer">Signed by</label>' +
                '<input class="sigfield" id="signer" name="signer" placeholder="your name" maxlength="80" spellcheck="false">' +
                '<button class="btn" id="sign" type="submit">Sign</button>' +
              '</div>' +
              '<span class="mouth" aria-hidden="true"></span>' +
              '<p class="sr" id="sign-status" aria-live="polite"></p>' +
            '</form>' +
          '</div>' +
        '</aside>' +
        '<div class="monitor">' +
          '<div class="inset"><div class="crt">' +
            '<div class="flicker"></div><div class="sweep"></div>' +
            '<div class="term" id="term" tabindex="0" aria-label="Dossier">' +
              '<div class="t-top"><span class="inv">' + esc(d.branch) + '</span><span id="sigstate" class="dim">' + esc(d.head || '') + '</span></div>' +
              '<div class="tiers">' + tiers + '</div>' +
              (human.length ?
                '<div class="sec-h"><span class="inv" style="background:var(--t-argued)">DECIDE</span><span class="rule"></span><span id="pickcount"></span></div>' +
                human.map(function (c) { return ownerRow(d, c); }).join('') : '') +
              (machine.length ?
                '<div class="sec-h"><span class="inv">SETTLED</span><span class="rule"></span><span class="dim">' + machine.length + '</span></div>' +
                '<div>' + machine.map(function (c) { return machineRow(d, c); }).join('') + '</div>' : '') +
              '<div class="sec-h"><span class="inv">LEDGER</span><span class="rule"></span></div>' +
              '<div class="lists">' +
                list('NOT CHECKED', d.not_checked, esc, true) +
                list('NO CLAIM', d.uncovered_diff_parts, function (p) { return '<code>' + esc(p) + '</code>'; }, true) +
                list('FOUND', d.found, esc) +
                list('REFUSED', d.refused, function (r) { return r && typeof r === 'object' ? '<b>' + esc(r.what) + '</b> — ' + esc(r.why) : esc(r); }) +
                list('SCOPE DRIFT', d.scope_drift, esc, true) +
              '</div>' +
              '<div class="prompt" id="prompt"></div>' +
            '</div>' +
          '</div></div>' +
          '<div class="foot"><span class="badge"></span><span class="led on"></span>' +
            '<span class="grill"><span></span><span></span><span></span><span></span><span></span></span>' +
            '<span class="sticker st-star" aria-hidden="true">★</span>' +
            (d.sample ? '<span class="sticker st-sample">SAMPLE</span>' : '') +
            '<span class="slot"></span></div>' +
        '</div>' +
      '</section>';

    var signer = document.getElementById('signer');
    signer.value = store('et:name') || '';
    signer.addEventListener('input', function () { store('et:name', signer.value); refresh(); });
    document.getElementById('printer').addEventListener('submit', function (e) { e.preventDefault(); sign(); });
    app.querySelectorAll('.keys input').forEach(function (inp) {
      inp.addEventListener('change', function () { setPick(inp.dataset.claim, inp.value, false); });
    });
    app.querySelectorAll('[data-jump]').forEach(function (b) {
      b.addEventListener('click', function () {
        var t = b.dataset.jump;
        var c = claims(d).filter(function (x) { return x.tier === t; })
          .sort(function (a, b2) { return String(a.id).localeCompare(String(b2.id)); })[0];
        var el = c && document.getElementById('row-' + c.id);
        if (!el) return;
        if (el.tagName === 'DETAILS') el.open = true;
        el.scrollIntoView({ block: 'start' });
        var f = el.tagName === 'DETAILS' ? el.querySelector('summary') : el.querySelector('input');
        if (f) f.focus({ preventScroll: true });
      });
    });
    if (state.receipt) printSlip(state.receipt, false);
    refresh();
  }

  function setPick(id, v, rerenderRadio) {
    state.picks[id] = v;
    store('et:picks:' + state.key, state.picks);
    if (rerenderRadio) {
      var inp = app.querySelector('.keys input[data-claim="' + CSS.escape(id) + '"][value="' + v + '"]');
      if (inp) inp.checked = true;
    }
    refresh();
  }

  function refresh() {
    var d = DATA[state.key]; if (!d) return;
    var human = humanOf(d);
    var picked = human.filter(function (c) { return state.picks[c.id]; }).length;
    human.forEach(function (c) {
      var row = document.getElementById('row-' + c.id);
      if (row) row.classList.toggle('picked', !!state.picks[c.id]);
      var led = app.querySelector('[data-led="' + CSS.escape(c.id) + '"]');
      if (led) led.classList.toggle('on', !!state.picks[c.id]);
    });
    var signer = document.getElementById('signer');
    var ready = picked === human.length && signer && signer.value.trim().length > 0;
    var btn = document.getElementById('sign');
    if (btn) {
      btn.disabled = !ready;
      btn.setAttribute('aria-describedby', 'sign-status');
    }
    var pc = document.getElementById('pickcount');
    if (pc) pc.innerHTML = '<span style="color:' + (picked === human.length ? 'var(--ph)' : 'var(--t-argued)') + '">' + picked + '/' + human.length + '</span>';
    var st = document.getElementById('sign-status');
    if (st) st.textContent = picked < human.length ? (human.length - picked) + ' still to pick' : (!ready ? 'type your name' : 'ready to sign');
    var ss = document.getElementById('sigstate');
    if (ss && state.receipt) { ss.className = 'state-signed'; ss.textContent = '✎ SIGNED · ' + state.receipt.signed_by; }
    var pr = document.getElementById('prompt');
    if (pr) {
      pr.innerHTML = state.justSigned || state.receipt
        ? '&gt; SIGNED <span class="dim">' + esc(state.receipt.signed_by) + ' · ' + esc(state.receipt.signed_at) + '</span>'
        : picked < human.length ? '&gt; ' + (human.length - picked) + ' TO PICK <span class="cursor"></span>'
        : '&gt; ◂ SIGN <span class="cursor"></span>';
    }
  }

  function buildReceipt(d, name) {
    var human = humanOf(d);
    var r = {
      branch: d.branch,
      head: d.head,
      signed_by: name,
      signed_at: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
      picks: human.map(function (c) { return { id: c.id, tier: c.tier, pick: state.picks[c.id], claim: c.claim || '' }; }),
      auto_settled: claims(d).filter(function (c) { return MACHINE[c.tier]; }).map(function (c) { return { id: c.id, tier: c.tier }; }),
      not_checked: (d.not_checked || []).slice(),
      uncovered_diff_parts: (d.uncovered_diff_parts || []).slice()
    };
    if (d.sample) r.sample = true;
    return r;
  }

  function sign() {
    var d = DATA[state.key];
    var name = document.getElementById('signer').value.trim();
    var human = humanOf(d);
    if (!name || human.some(function (c) { return !state.picks[c.id]; })) return;
    state.receipt = buildReceipt(d, name);
    state.justSigned = true;
    printSlip(state.receipt, true);
    refresh();
    var st = document.getElementById('sign-status');
    if (st) st.textContent = 'Signed by ' + name + '. Receipt printed.';
  }

  function printSlip(r, animate) {
    var d = DATA[state.key];
    var feed = document.getElementById('feed');
    var tools = document.getElementById('slip-tools');
    var auto = (r.auto_settled || []);
    var html =
      '<div class="slip' + (animate ? ' printing' : '') + '" role="document" aria-label="Receipt">' +
      '<div class="ink">' +
        '<h3>RECEIPT</h3>' +
        '<div style="text-align:center" class="sub">' + esc(r.branch) + ' @ ' + esc(r.head) + (r.sample ? '<br>SAMPLE' : '') + '</div>' +
        '<hr class="rule">' +
        (r.picks || []).map(function (p) {
          return '<div class="ln"><span>' + (GLYPH[p.tier] || '') + ' ' + esc(p.id) + '</span><span class="sub">' + esc(String(p.tier).toUpperCase()) + '</span>' +
            '<span class="pk ' + esc(String(p.pick).replace(' ', '-')) + '">' + esc(String(p.pick).toUpperCase()) + '</span></div>' +
            '<div class="cl">' + esc(p.claim) + '</div>';
        }).join('') +
        '<hr class="rule">' +
        (auto.length ? '<div class="auto"><span class="sub">AUTO</span>' + auto.map(function (a) {
          return '<span title="' + esc(a.tier) + '">' + (GLYPH[a.tier] || '') + ' ' + esc(a.id) + '</span>';
        }).join('') + '</div><hr class="rule">' : '') +
        ((r.not_checked || []).length ? '<div class="sub">NOT CHECKED</div><ul>' + r.not_checked.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '') +
        ((r.uncovered_diff_parts || []).length ? '<div class="sub" style="margin-top:6px">NO CLAIM</div><ul class="paths">' + r.uncovered_diff_parts.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '') +
        '<hr class="rule">' +
        '<div class="sig"><span class="sub">SIGNED</span><span class="who">' + esc(r.signed_by) + '</span>' +
        '<span class="sub">AT</span><span>' + esc(r.signed_at) + '</span></div>' +
      '</div><span class="tear"></span></div>';
    feed.innerHTML = html;
    var side = feed.closest('.side'); if (side) side.classList.add('signed');
    var raw = '<div class="slip raw" role="document" aria-label="Receipt JSON"><div class="ink">' + esc(JSON.stringify(r, null, 2)) + '</div><span class="tear"></span></div>';
    var stub = document.getElementById('stub'); if (stub) stub.hidden = true;
    tools.innerHTML =
      '<div class="slip-tools"><button type="button" class="btn ghost" id="showjson" aria-pressed="false">JSON</button>' +
      '<button type="button" class="btn" id="dl">Download</button></div>';
    document.getElementById('dl').addEventListener('click', function () { download(r); });
    document.getElementById('showjson').addEventListener('click', function (e) {
      var on = e.currentTarget.getAttribute('aria-pressed') !== 'true';
      e.currentTarget.setAttribute('aria-pressed', String(on));
      feed.innerHTML = on ? raw : html.replace(' printing', '');
      feed.scrollTop = feed.scrollHeight;
    });
    placeFeed();
    feed.scrollTop = feed.scrollHeight;
    if (animate) {
      var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (!reduce) feed.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  function placeFeed() {
    var z = document.getElementById('pzone'), pr = document.getElementById('printer');
    if (!z || !pr) return;
    var y = z.getBoundingClientRect().bottom - pr.getBoundingClientRect().top - 14;
    z.style.setProperty('--slot-y', Math.round(y) + 'px');
  }
  window.addEventListener('resize', placeFeed);

  function download(r) {
    var blob = new Blob([JSON.stringify(r, null, 2) + '\n'], { type: 'application/json' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (r.sample ? '_sample' : r.branch) + '.json';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  /* ---------- keyboard ---------- */
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var t = e.target;
    var typing = t && (t.tagName === 'INPUT' && t.type !== 'radio' || t.tagName === 'TEXTAREA');
    if (typing) return;
    if (e.key === 'Escape' && state.key) { location.hash = '#/'; return; }
    var row = t && t.closest && t.closest('.own');
    if (!row) return;
    var m = { a: 'accept', r: 'reject', s: 'send back' }[e.key.toLowerCase()];
    if (!m) return;
    e.preventDefault();
    setPick(row.dataset.id, m, true);
    var inp = row.querySelector('input[value="' + m + '"]');
    if (inp) inp.focus();
  });

  /* ---------- routing ---------- */
  function route() {
    clearInterval(clockTimer);
    var h = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
    var m = h.match(/^d\/(.+)$/);
    if (m) renderDossier(m[1]);
    else { state.key = null; renderLanding(); }
    window.scrollTo(0, 0);
    if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
    app.focus({ preventScroll: true });
    var d = m && DATA[m[1]];
    document.title = d ? (d.issue != null ? '#' + d.issue + ' · ' : '') + 'Earned Trust' : 'Earned Trust';
  }
  var skip = document.querySelector('.skip');
  if (skip) skip.addEventListener('click', function (e) {
    e.preventDefault();
    var t = document.querySelector('.own input, .blist a, #term') || app;
    t.focus();
  });
  window.addEventListener('hashchange', route);
  route();
})();
