/* Earned Trust — owner view. No build step; data comes from data.js (window.DOSSIERS). */
(function () {
  'use strict';

  var TIERS = ['Proved', 'Tested', 'Measured', 'Argued', 'Refused'];
  var MACHINE = { Proved: 1, Tested: 1, Measured: 1 };
  var GLYPH = { Proved: '■', Tested: '▲', Measured: '●', Argued: '◆', Refused: '✕' };
  /* What each tier means, from CONVENTIONS.md (tier rules). `long` on the landing page, `short` under the dossier counters. */
  var DEF = {
    Proved: { long: 'A checker confirmed it on the real code, with no gaps.', short: 'A checker confirmed it on the real code.' },
    Tested: { long: 'A test fails before the change and passes after it.', short: 'A test fails before, passes after.' },
    Measured: { long: 'A tool produced a number, and the number is the evidence.', short: 'A number from a tool.' },
    Argued: { long: 'No check settles it; it rests on reasoning. You decide.', short: 'No check settles it. You decide.' },
    Refused: { long: 'It touches public API, wire format, warnings or security, so the tool refuses to grade it. You decide.', short: 'Touches API, wire format, warnings or security. You decide.' }
  };
  var RESULT = {
    pass: { w: 'PASS', t: 'The check ran and got its expected outcome. This is the check\u2019s own result, not a verdict on the claim.' },
    fail: { w: 'FAIL', t: 'The check ran and did not get its expected outcome. Read the line beside it for what that shows.' },
    error: { w: 'INCOMPLETE', t: 'The check could not run every case here.' }
  };
  var NUM = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];
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
  function rich(s) { return esc(s).replace(/`([^`]+)`/g, '<code class="ic">$1</code>'); }
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
    var defs = TIERS.map(function (t) {
      return '<dt class="c-' + lc(t) + '"><span aria-hidden="true">' + GLYPH[t] + '</span> ' + t + '</dt><dd>' + esc(DEF[t].long) + '</dd>';
    }).join('');
    var real = ks.filter(function (k) { return !DATA[k].sample; }).length;
    var nIssues = (NUM[real] || String(real)) + ' issue' + (real === 1 ? '' : 's');

    app.innerHTML =
      '<section class="landing">' +
        '<div class="hero">' +
          '<h1><span>Read the evidence,</span><em>not the diff.</em></h1>' +
          '<p class="lede">An AI agent fixed ' + nIssues + ' in MessagePack-CSharp. Each fix is split into claims, and each claim is graded by the evidence behind it. Machines settle what they can; you decide the rest and sign.</p>' +
          '<div class="ladder">' + caps +
            '<span class="bracket machine">settled by machine</span><span class="bracket owner">you decide</span>' +
          '</div>' +
          '<dl class="defs">' + defs + '</dl>' +
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
    if (window.EarnedTrustPitch) window.EarnedTrustPitch.mount(app, DATA);
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
  function shortPath(p) {
    var m = String(p).match(/^(.*\/)?([^\/:]+)(:.*)?$/);
    return m ? '<span class="dir">' + esc(m[1] || '') + '</span><b>' + esc(m[2]) + '</b>' + (m[3] ? '<span class="ln">' + esc(m[3]) + '</span>' : '') : esc(p);
  }
  function hunkHtml(h) {
    var ind = h.lines.reduce(function (m, l) {
      if (!l[3].trim()) return m;
      var n = l[3].match(/^[ \t]*/)[0].length; return Math.min(m, n);
    }, 1e9);
    if (ind === 1e9) ind = 0;
    return '<div class="hunk">' + (h.file ? '<div class="hh"><span>' + esc(h.file) + '</span></div>' : '') +
      '<table><tbody>' + h.lines.map(function (l) {
        var cls = l[0] === '+' ? 'add' : l[0] === '-' ? 'del' : '';
        return '<tr class="' + cls + '"><td class="no">' + (l[1] == null ? '' : l[1]) + '</td><td class="no">' + (l[2] == null ? '' : l[2]) +
          '</td><td class="op">' + (l[0] === ' ' ? '' : l[0]) + '</td><td class="tx">' + esc(l[3].slice(ind)) + '</td></tr>';
      }).join('') + (h.cut ? '<tr class="cut"><td colspan="4">… ' + h.cut + ' more lines</td></tr>' : '') + '</tbody></table></div>';
  }
  function sourceBlock(d, parts) {
    var src = d._source && d._source.parts || {};
    return '<div class="srcs"><div class="cap-l">Code this claim covers</div>' + parts.map(function (p) {
      var s = src[p];
      var gh = s ? '<a class="gh" href="' + esc(s.url) + '" target="_blank" rel="noopener">GitHub ↗</a>' : '';
      if (!s || !s.shown.length) return '<div class="src none"><span class="sp">' + shortPath(p) + '</span>' + gh + '</div>';
      var nm = s.hunks - s.shown.length;
      var more = nm > 0 ? '<div class="more">' + nm + ' more change' + (nm === 1 ? '' : 's') + ' in ' + s.files + ' files · ' + gh + '</div>' : '';
      return '<details class="src"><summary><span class="sp">' + shortPath(p) + '</span>' +
        (s.files > 1 ? '<span class="cnt">' + s.files + ' files</span>' : '') + gh + '</summary>' +
        s.shown.map(function (h) { return hunkHtml(s.files > 1 ? h : { head: h.head, lines: h.lines, cut: h.cut }); }).join('') + more + '</details>';
    }).join('') + '</div>';
  }
  function evDetails(ev) {
    var x = {};
    Object.keys(ev).forEach(function (k) { if (['check', 'branch', 'result', 'summary', 'command', 'produced_by'].indexOf(k) < 0) x[k] = ev[k]; });
    return esc(JSON.stringify(x, null, 2));
  }
  function evidenceBlock(d, c, seen) {
    var out = '';
    var chain = Array.isArray(c.chain) ? c.chain : [];
    if (chain.length) {
      out += '<div class="chain">' + chain.map(function (l, i) {
        return '<span class="lk c-' + lc(l.tier) + '">' + (GLYPH[l.tier] || '·') + ' ' + esc(l.tier) + '<span>' + esc(l.link) + '</span></span>';
      }).join('') + '</div>';
    }
    (c.evidence || []).forEach(function (ref) {
      var ev = (d._evidence || {})[ref];
      var name = String(ref).split('/').pop().replace(/\.json$/, '').replace(/[-_.]+/g, ' ');
      var res = ev ? lc(ev.result) || 'missing' : 'missing';
      var rw = RESULT[res] || { w: ev ? String(ev.result || '?').toUpperCase() : 'MISSING', t: ev ? '' : 'No evidence file found.' };
      var again = seen && seen[ref];
      if (seen) seen[ref] = 1;
      var sum = ev ? rich(ev.summary || '') : '';
      out += '<details class="evl"><summary>' +
        '<span class="res ' + esc(res) + '" title="' + esc(rw.t) + '">' + esc(rw.w) + '</span>' +
        '<span class="evn">' + esc(name) + (ev && ev.produced_by === 'hand' ? ' <span class="hand" title="A person or agent ran this by hand, not a script.">by hand</span>' : '') + '</span>' +
        '<span class="evs">' + (again ? '<span class="again">Same check as above.</span>' : sum) + '</span></summary>' +
        '<div class="evb">' +
          (again && sum ? '<p class="evs">' + sum + '</p>' : '') +
          (ev && ev.command ? '<div class="cmd"><code>' + esc(ev.command) + '</code></div>' : '') +
          (ev ? '<details class="rawout"><summary>Show raw output</summary><pre class="evjson">' + evDetails(ev) + '</pre></details>' : '') +
          '<a class="raw" href="../' + esc(ref) + '" target="_blank" rel="noopener">' + esc(ref) + ' ↗</a>' +
        '</div></details>';
    });
    if (c.requirement) {
      var rt = (d._requirements || {})[c.requirement];
      out += '<div class="req"><span class="rid" title="' + esc(c.requirement) + '">Requirement' + (c.requirement_inferred ? ' <span class="inf" title="Our reading of the issue, not its text">· our reading</span>' : '') + '</span>' +
        '<span class="rt">' + (rt ? rich(rt) : esc(c.requirement)) + '</span></div>';
    }
    if ((c.diff_parts || []).length) out += sourceBlock(d, c.diff_parts);
    return out ? '<div class="ev">' + out + '</div>' : '';
  }

  function ownerRow(d, c, seen) {
    var pick = state.picks[c.id];
    var name = 'pick-' + c.id;
    return '<article class="own c-' + lc(c.tier) + (pick ? ' picked' : '') + '" id="row-' + esc(c.id) + '" data-id="' + esc(c.id) + '" tabindex="-1">' +
      '<div class="own-h"><span class="tg">' + GLYPH[c.tier] + ' ' + esc(c.tier.toUpperCase()) + '</span><span class="id">' + esc(c.id) + '</span>' +
        (c.owner_role ? '<span class="role" title="Who should decide this claim">For: ' + esc(c.owner_role) + '</span>' : '') + '</div>' +
      '<p class="claim-t">' + rich(c.claim) + '</p>' +
      (c.why_this_tier ? '<p class="why">' + rich(c.why_this_tier) + '</p>' : '') +
      evidenceBlock(d, c, seen) +
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
      '<span class="ct">' + rich(c.claim) + '</span><span class="tw" aria-hidden="true">▸</span></summary>' +
      '<div class="body">' + (c.why_this_tier ? '<p class="why">' + rich(c.why_this_tier) + '</p>' : '') + evidenceBlock(d, c) + '</div>' +
    '</details>';
  }

  function list(title, gloss, items, fmt, hot, emptyText) {
    items = Array.isArray(items) ? items : [];
    if (!items.length && !emptyText) return '';
    return '<section class="lst' + (hot && items.length ? ' hot' : '') + '"><h4><span class="inv">' + title + '</span><span class="k">' + items.length + '</span></h4>' +
      '<p class="gloss">' + esc(items.length ? gloss : emptyText) + '</p>' +
      (items.length ? '<ul>' + items.map(function (x) { return '<li>' + fmt(x) + '</li>'; }).join('') + '</ul>' : '') + '</section>';
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
          '<span class="gl">' + esc(DEF[t].short) + '</span>' +
        '</button>';
    }).join('');

    var seen = {};
    var leds = human.map(function (c) { return '<span class="led" data-led="' + esc(c.id) + '"></span>'; }).join('');

    app.innerHTML =
      '<section class="dossier">' +
        '<aside class="side">' +
          '<div class="issue-no">' + issueNo + '</div>' +
          '<h1 class="issue-title">' + esc(d.title || d.branch) + '</h1>' +
          (d.summary ? '<div class="changed"><h2>What the AI changed</h2><p>' + rich(d.summary) + '</p></div>' : '') +
          '<dl class="meta">' +
            '<dt>branch</dt><dd>' + esc(d.branch) + '</dd>' +
            '<dt>commits</dt><dd>' + (d._source && d._source.compare ? '<a href="' + esc(d._source.compare) + '" target="_blank" rel="noopener">' + esc(d.base || '?') + ' → ' + esc(d.head || '?') + ' ↗</a>' : esc(d.base || '?') + ' → ' + esc(d.head || '?')) + '</dd>' +
            (diff.files != null ? '<dt>changed</dt><dd>' + esc(diff.files) + ' files <span class="add">+' + esc(diff.insertions) + '</span> <span class="del">−' + esc(diff.deletions) + '</span></dd>' : '') +
          '</dl>' +
          '<div class="printer-zone" id="pzone">' +
            '<div class="feed" id="feed"></div>' +
            '<form class="printer" id="printer" autocomplete="off">' +
              '<span class="stub" id="stub" aria-hidden="true"></span>' +
              '<div class="p-top"><h2 class="p-h">Sign the receipt</h2><div class="p-leds" aria-hidden="true">' + leds + '</div><div id="slip-tools"></div></div>' +
              '<p class="p-sub">Signing records your decisions, what machines settled and what nobody checked, for commit ' + esc(d.head || '') + '.</p>' +
              '<div class="p-row">' +
                '<label class="sr" for="signer">Your name</label>' +
                '<input class="sigfield" id="signer" name="signer" placeholder="Your name" maxlength="80" spellcheck="false">' +
                '<button class="btn" id="sign" type="submit">Sign</button>' +
              '</div>' +
              '<span class="mouth" aria-hidden="true"></span>' +
              '<p class="p-status" id="sign-status" aria-live="polite"></p>' +
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
                '<div class="sec-h"><span class="inv" style="background:var(--t-argued)">YOUR CALL</span><span class="rule"></span><span id="pickcount"></span></div>' +
                '<p class="sec-g">No machine can settle these. Read the evidence, then accept, reject, or send the claim back to the AI to rework. PASS or FAIL is each check\u2019s own outcome, not a verdict on the claim.</p>' +
                human.map(function (c) { return ownerRow(d, c, seen); }).join('') : '') +
              (machine.length ?
                '<div class="sec-h"><span class="inv">SETTLED</span><span class="rule"></span><span class="dim">' + machine.length + '</span></div>' +
                '<p class="sec-g">A machine check graded these. Open one to see its evidence.</p>' +
                '<div>' + machine.map(function (c) { return machineRow(d, c); }).join('') + '</div>' : '') +
              '<div class="sec-h"><span class="inv">LEDGER</span><span class="rule"></span></div>' +
              '<div class="lists">' +
                list('NOT CHECKED', 'What we did not verify.', d.not_checked, rich, true) +
                list('NO CLAIM', 'Changed code that no claim covers.', d.uncovered_diff_parts, function (p) { return '<code>' + esc(p) + '</code>'; }, true, 'Every changed line is covered by a claim.') +
                list('FOUND', 'What the reviewer found.', d.found, rich) +
                list('REFUSED', 'Why some claims are left to a person.', d.refused, function (r) { return r && typeof r === 'object' ? '<b>' + rich(r.what) + '</b> — ' + rich(r.why) : rich(r); }) +
                list('SCOPE DRIFT', 'Changes the issue did not ask for.', d.scope_drift, rich, true) +
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
    if (pc) pc.innerHTML = '<span style="color:' + (picked === human.length ? 'var(--ph)' : 'var(--t-argued)') + '">' + picked + ' of ' + human.length + ' decided</span>';
    var st = document.getElementById('sign-status');
    if (st && !state.receipt) st.textContent = picked < human.length ? 'Decide all ' + human.length + ' claims to sign (' + (human.length - picked) + ' left).' : (!ready ? 'Type your name to sign.' : 'Ready to sign.');
    if (st && state.receipt && !state.justSigned) st.textContent = 'Signed by ' + state.receipt.signed_by + '.';
    var ph = app.querySelector('.p-h');
    if (ph) ph.textContent = state.receipt ? 'Receipt' : 'Sign the receipt';
    var psub = app.querySelector('.p-sub');
    if (psub) psub.hidden = !!state.receipt;
    var ss = document.getElementById('sigstate');
    if (ss && state.receipt) { ss.className = 'state-signed'; ss.textContent = '✎ SIGNED · ' + state.receipt.signed_by; }
    var pr = document.getElementById('prompt');
    if (pr) {
      pr.innerHTML = state.justSigned || state.receipt
        ? '&gt; SIGNED <span class="dim">' + esc(state.receipt.signed_by) + ' · ' + esc(state.receipt.signed_at) + '</span>'
        : picked < human.length ? '&gt; ' + (human.length - picked) + ' TO DECIDE <span class="cursor"></span>'
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
        (auto.length ? '<div class="sub">SETTLED BY MACHINE</div><div class="auto">' + auto.map(function (a) {
          return '<span title="' + esc(a.tier) + '">' + (GLYPH[a.tier] || '') + ' ' + esc(a.id) + '</span>';
        }).join('') + '</div><hr class="rule">' : '') +
        ((r.not_checked || []).length ? '<div class="sub">NOT CHECKED</div><ul>' + r.not_checked.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '') +
        ((r.uncovered_diff_parts || []).length ? '<div class="sub" style="margin-top:6px">UNCOVERED CODE</div><ul class="paths">' + r.uncovered_diff_parts.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '') +
        '<hr class="rule">' +
        '<div class="sig"><span class="sub">SIGNED</span><span class="who">' + esc(r.signed_by) + '</span>' +
        '<span class="sub">AT</span><span>' + esc(r.signed_at.replace('T', ' ').replace(/Z$/, ' UTC')) + '</span></div>' +
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
    /* the receipt grows up from the printer but stops below the issue title, which stays visible */
    var t = document.querySelector('.side .issue-title');
    if (t) z.style.setProperty('--feed-max', Math.max(160, Math.round(pr.getBoundingClientRect().top + 14 - t.getBoundingClientRect().bottom - 18)) + 'px');
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
    if (window.EarnedTrustPitch && window.EarnedTrustPitch.unmount) window.EarnedTrustPitch.unmount();
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
