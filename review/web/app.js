/* Earned Trust — owner view. No build step; data comes from data.js (window.DOSSIERS). */
(function () {
  'use strict';

  /* Confidence bands from confidence.json, plus the owner gate. `long` on the landing page, `short` under the dossier counters. */
  var BANDS = ['high', 'medium', 'low'];
  var GROUPS = BANDS.concat('owner');
  var BAND = {
    high: { g: '●', w: 'High', long: 'A strong check backs it: a proof, a rebuild, or a test that fails before and passes after.', short: 'A strong check backs it.' },
    medium: { g: '◐', w: 'Medium', long: 'An experiment on the real code, or a weaker check, backs it.', short: 'Some check backs it.' },
    low: { g: '○', w: 'Low', long: 'Only a number, or no check at all. Read it yourself.', short: 'Little or no check.' },
    owner: { g: '✎', w: 'Needs owner', long: 'Something users rely on changed, or no test reaches a changed line. Its owner decides, and you sign.', short: 'A promise changed or is untested. Owner decides.' }
  };
  var RESULT = {
    pass: { w: 'PASS', t: 'The check ran and got its expected outcome. This is the check\u2019s own result, not a verdict on the claim.' },
    fail: { w: 'FAIL', t: 'The check ran and did not get its expected outcome. Read the line beside it for what that shows.' },
    error: { w: 'INCOMPLETE', t: 'The check could not run every case here.' }
  };
  /* plain labels for confidence.json signal kinds */
  var KIND = {
    'rebuild-compare': 'rebuilt and compared', 'old-vs-new-run': 'old and new code, same output', 'proof-model': 'formal verification', 'flip-test': 'fails before, passes after',
    'revert-test': 'fails when the fix is undone', probe: 'experiment on the real code', count: 'number from a tool', none: 'no check'
  };
  /* what a new test shows, from explain-check.json results/verdict */
  var TK = {
    flip: { g: '✓', row: 'proves the fix', one: 'proves the fix', many: 'prove the fix',
      say: 'This test proves the fix: it fails on the old code and passes on the new.' },
    weak: { g: '⚠', row: 'already passed before the fix', one: 'already passed before', many: 'already passed before',
      say: 'This test passed before the fix too, so it doesn\u2019t prove the fix.' },
    norun: { g: '∅', row: 'couldn\u2019t run here', one: 'couldn\u2019t run', many: 'couldn\u2019t run',
      say: 'This test couldn\u2019t run here, so it doesn\u2019t prove anything yet.' },
    other: { g: '·', row: 'unclear result', one: 'unclear', many: 'unclear', say: '' }
  };
  var OUT = { pass: 'passes', fail: 'fails', build_failed: 'doesn\u2019t build' };
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
  function confOf(d, c) { return cf(d, c.id) || { score: 0, band: 'low' }; }
  function byId(a, b) { return String(a.id).localeCompare(String(b.id)); }
  /* claims whose evidence shows a changed contract: the owner decides these */
  function humanOf(d) { return claims(d).filter(function (c) { return confOf(d, c).gate; }).sort(byId); }
  /* every other claim, strongest evidence first */
  function machineOf(d) {
    return claims(d).filter(function (c) { return !confOf(d, c).gate; }).sort(function (a, b) {
      return confOf(d, b).score - confOf(d, a).score || byId(a, b);
    });
  }
  function counts(d) {
    var n = { high: 0, medium: 0, low: 0, owner: 0 };
    claims(d).forEach(function (c) { var x = confOf(d, c); if (n[x.band] != null) n[x.band]++; if (x.gate) n.owner++; });
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
    var cs = humanOf(d).concat(machineOf(d));
    return '<span class="strip" aria-hidden="true">' + cs.map(function (c) {
      var x = confOf(d, c);
      return '<i class="bn-' + esc(x.band) + (x.gate ? ' human' : '') + '"></i>';
    }).join('') + '</span>';
  }

  /* ---------- landing ---------- */
  function renderLanding() {
    mastRight.innerHTML = '<a href="#/rules" style="text-decoration:none">learned rules ▸</a>';
    var ks = keys();
    var items = ks.map(function (k) {
      var d = DATA[k], h = humanOf(d), r = d._receipt;
      var st = r ? '<span class="state-signed">SIGNED</span>'
        : h.length ? '<span style="color:var(--t-argued)">' + h.length + ' OPEN</span>'
        : '<span class="dim">SETTLED</span>';
      var n = counts(d), lbl = GROUPS.filter(function (t) { return n[t]; }).map(function (t) { return n[t] + ' ' + BAND[t].w; }).join(', ');
      return '<li><a href="#/d/' + encodeURIComponent(k) + '" aria-label="' + esc(d.branch + ': ' + (d.title || '') + '. ' + lbl + (r ? '. Signed.' : '')) + '">' +
        '<span class="arrow" aria-hidden="true">▸</span>' +
        '<span class="bname">' + esc(d.branch || k) + (d.sample ? ' <span class="dim">· sample</span>' : '') + '</span>' +
        '<span class="bstate">' + st + '</span>' +
        '<span class="bt">' + esc(d.title || '') + '</span>' +
        strip(d) +
        '<span class="gc" aria-hidden="true">' + GROUPS.map(function (t) {
          return '<span class="bn-' + t + (n[t] ? '' : ' z') + '">' + BAND[t].g + n[t] + '</span>';
        }).join('') + '</span></a></li>';
    }).join('') || '<li class="empty dim">NO DOSSIERS — run render_web.py</li>';

    var caps = GROUPS.map(function (t, i) {
      return (i === 3 ? '<span class="gap"></span>' : '') +
        '<div class="cap ' + t + '" title="' + esc(BAND[t].long) + '"><b aria-hidden="true">' + BAND[t].g + '</b><i>' + BAND[t].w + '</i><span class="sr">: ' + esc(BAND[t].long) + '</span></div>';
    }).join('');
    var real = ks.filter(function (k) { return !DATA[k].sample; }).length;
    var nIssues = (NUM[real] || String(real)) + ' issue' + (real === 1 ? '' : 's');

    app.innerHTML =
      '<section class="landing">' +
        '<div class="hero">' +
          '<h1><span>Trace decisions,</span><em>not lines.</em></h1>' +
          '<p class="lede">An AI agent fixed ' + nIssues + ' in MessagePack-CSharp. A script checks every decision. Where users would notice, the owner decides.</p>' +
          '<div class="ladder">' + caps +
            '<span class="bracket machine">scored by evidence</span><span class="bracket owner">owner decides</span>' +
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
  /* script summaries say base/branch; show them as before/after the change */
  function plain(t) {
    return String(t == null ? '' : t)
      .replace(/\b(on|in) (base|branch)\b/g, function (m, p, w) { return w === 'base' ? 'before the change' : 'after the change'; })
      .replace(/\b[Bb]ase\b/g, function (w) { return w[0] === 'B' ? 'Before the change' : 'before the change'; })
      .replace(/\b[Bb]ranch\b/g, function (w) { return w[0] === 'B' ? 'After the change' : 'after the change'; });
  }
  function evidenceBlock(d, c) {
    var out = '', n = 0;
    if (c.why_this_tier) out += '<p class="why">' + rich(c.why_this_tier) + '</p>';
    var chain = Array.isArray(c.chain) ? c.chain : [];
    if (chain.length) {
      out += '<div class="cap-l">Chain of evidence · as strong as its weakest link</div><div class="chain">' + chain.map(function (l) {
        return '<span class="lk"><span>' + rich(l.link) + '</span></span>';
      }).join('') + '</div>';
    }
    (c.evidence || []).forEach(function (ref) {
      var ev = (d._evidence || {})[ref];
      var name = base(ref).replace(/\.json$/, '').replace(/[-_.]+/g, ' ');
      var res = ev ? lc(ev.result) || 'missing' : 'missing';
      var rw = RESULT[res] || { w: ev ? String(ev.result || '?').toUpperCase() : 'MISSING', t: ev ? '' : 'No evidence file found.' };
      var sum = ev ? plain(ev.summary || '') : '';
      n++;
      out += '<details class="evl"><summary title="' + esc(sum) + '">' +
        '<span class="res ' + esc(res) + '" title="' + esc(rw.t) + '">' + esc(rw.w) + '</span>' +
        '<span class="evn">' + esc(name) + (ev && ev.produced_by === 'hand' ? ' <span class="hand" title="A person or agent ran this by hand, not a script.">by hand</span>' : '') + '</span></summary>' +
        '<div class="evb">' +
          (sum ? '<p class="evs">' + rich(sum) + '</p>' : '') +
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
    return out ? '<details class="evd"><summary>evidence' + (n ? ' <span class="k">' + n + '</span>' : '') + ' <span class="tw" aria-hidden="true">▸</span></summary><div class="ev">' + out + '</div></details>' : '';
  }

  function ownerRow(d, c) {
    var pick = state.picks[c.id];
    var name = 'pick-' + c.id, x = confOf(d, c), dc = decOf(d, c.id);
    return '<article class="own bn-owner' + (pick ? ' picked' : '') + '" id="row-' + esc(c.id) + '" data-id="' + esc(c.id) + '" data-band="owner" tabindex="-1">' +
      '<div class="own-h">' + scoreHtml(x) + '<span class="id">' + esc(c.id) + '</span>' + needsBadge(x) + '</div>' +
      (dc ? '<p class="claim-t">' + esc(dc.title) + '</p>' + gateBlock(x, c.owner_role) + '<div class="dc">' + decisionPanes(dc) + '</div>' + receiptBlock(d, x) + filesBlock(d, c)
          : '<p class="claim-t">' + rich(c.claim) + '</p>' + gateBlock(x, c.owner_role) + receiptBlock(d, x) + evidenceBlock(d, c)) +
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
    var x = confOf(d, c), dc = decOf(d, c.id);
    return '<details class="mach bn-' + esc(x.band) + (dc ? ' dc' : '') + '" id="row-' + esc(c.id) + '" data-band="' + esc(x.band) + '">' +
      '<summary><span class="tn">' + scoreHtml(x) + '</span><span class="id">' + esc(c.id) + '</span>' +
      '<span class="ct">' + needsBadge(x) + (dc ? esc(dc.title) : rich(c.claim)) + '</span><span class="tw" aria-hidden="true">▸</span></summary>' +
      '<div class="body">' + gateBlock(x) + (dc ? decisionPanes(dc) + receiptBlock(d, x) + filesBlock(d, c) : receiptBlock(d, x) + evidenceBlock(d, c)) + '</div>' +
    '</details>';
  }

  function list(title, gloss, items, fmt, hot, emptyText) {
    items = Array.isArray(items) ? items : [];
    if (!items.length && !emptyText) return '';
    return '<section class="lst' + (hot && items.length ? ' hot' : '') + '"><h4><span class="inv">' + title + '</span><span class="k">' + items.length + '</span></h4>' +
      '<p class="gloss">' + esc(items.length ? gloss : emptyText) + '</p>' +
      (items.length ? '<ul>' + items.map(function (x) { return '<li>' + fmt(x) + '</li>'; }).join('') + '</ul>' : '') + '</section>';
  }

  function base(p) { return String(p || '').split('/').pop(); }
  function goto(id) { return '<button type="button" class="goto" data-goto="' + esc(id) + '">' + esc(id) + '</button>'; }
  function ruleLink(id, sources) {
    var s = sources || [];
    return (s[0] ? '<a class="rid" href="' + esc(s[0]) + '" target="_blank" rel="noopener" title="Where the maintainers said it">' + esc(id) + '</a>' : '<span class="rid">' + esc(id) + '</span>') +
      s.slice(1).map(function (u, i) { return '<a class="srcn" href="' + esc(u) + '" target="_blank" rel="noopener" aria-label="' + esc(id) + ' source ' + (i + 2) + '">' + (i + 2) + '</a>'; }).join('');
  }

  /* ---------- confidence (score, band, gate, receipt) ---------- */
  function cf(d, id) {
    var x = ((d._confidence || {}).details || {}).claims;
    return x && x[id] || null;
  }
  function scoreHtml(x) {
    if (!x) return '';
    var s = Math.max(0, Math.min(100, +x.score || 0));
    return '<span class="score sb-' + esc(x.band) + '" title="Score ' + s + ' of 100 · ' + esc(x.band) + '">' +
      '<span class="meter" aria-hidden="true"><b style="--s:' + s + '%"></b></span><span class="sn">' + s + '</span>' +
      '<span class="bd">' + esc(x.band || '') + '</span></span>';
  }
  function needsBadge(x) { return x && x.gate ? '<span class="needs" title="A promise to users changed; its owner decides">needs owner</span>' : ''; }
  /* the promise that changed, in plain words */
  var CONTRACT_WORDS = { diagnostics: 'warnings', generated: 'generated code', 'public-api': 'public API', 'compat-breaking': 'compatibility' };
  function capital(t) { return t.charAt(0).toUpperCase() + t.slice(1); }
  function gateBlock(x, role) {
    var g = x && x.gate;
    if (!g) return '';
    var rules = g.rules || [], area = CONTRACT_WORDS[g.contract] || g.contract;
    var m = /most commits on the (.+?) paths at base \((\d+) commits\)/.exec(g.owner_basis || '');
    var why = m ? esc(g.owner || 'This person') + ' has the most commits on the ' + esc(String(CONTRACT_WORDS[m[1]] || m[1]).replace(/ code$/, '')) + ' code (' + esc(m[2]) + ' commits), counted at the commit this change starts from.'
      : esc(g.owner_basis || 'Owner picked from commit history.');
    var ev = g.shown_by ? ' <a class="sf" href="../' + esc(g.shown_by) + '" target="_blank" rel="noopener">' + esc(base(g.shown_by)) + ' ↗</a>' : '';
    return '<details class="gate"><summary>' +
        '<span class="nd">Needs an owner:</span><span class="who"' + (role ? ' title="For: ' + esc(role) + '"' : '') + '>' + esc(g.owner || 'owner unknown') + '</span>' +
        '<span class="ctr">' + esc(area) + '</span><span class="tw" aria-hidden="true">▸</span></summary>' +
      '<div class="gb">' +
        '<div class="gq"><h6>Why</h6><p>' + (g.source === 'old-vs-new' ? '' : 'A real check showed: ') + rich(plain(capital(String(g.change || '').replace(/\(base reported it\)/, '(it was reported before the change)').replace(/\(base compiles\)/, '(it compiled before the change)')))) + '.' + ev + '</p>' +
          ((g.also || []).length ? '<ul class="rules">' + g.also.map(function (a) { return '<li><span></span><span>' + rich(plain(capital(a))) + '.</span></li>'; }).join('') + '</ul>' : '') +
          (g.inherited_from ? '<p>This decision depends on ' + goto(g.inherited_from) + ', which needs an owner, so it does too.</p>' : '') + '</div>' +
        '<div class="gq"><h6>Who decided</h6><p>A fixed rule, not the AI. The old and the new code run on the same inputs from before the change. If something users rely on comes out different, or no input runs a changed line at all, a person must decide. A high score never clears it, and the AI can’t either.</p></div>' +
        '<div class="gq"><h6>Why this person</h6><p>' + why + '</p></div>' +
        (rules.length ? '<div class="gq"><h6>What maintainers said before</h6><ul class="rules">' + rules.map(function (r) { return '<li><span>' + ruleLink(r.id, r.sources) + '</span><span>' + rich(r.rule) + '</span></li>'; }).join('') + '</ul></div>' : '') +
      '</div></details>';
  }
  function delta(n) { return (n < 0 ? '−' : '+') + Math.abs(n); }
  function receiptBlock(d, x) {
    if (!x) return '';
    var F = ((d._confidence || {}).details || {}).formula || {};
    var sigs = x.signals || [], con = x.contradicted_by || [], sh = x.shares_lines_with || [], dep = x.depends_on || [];
    var pick = sigs.length ? sigs.map(function (s) { return s.score; }).reduce(function (a, b) { return /weakest/.test(x.how) ? Math.min(a, b) : Math.max(a, b); }) : null;
    var body = sigs.map(function (s) {
      return '<div class="sgl' + (s.score === pick ? ' counts' : '') + '"><div class="sgh"><span>' + esc(KIND[s.kind] || s.kind) + '</span>' +
          (s.produced_by === 'hand' ? '<span class="hand">by hand</span>' : '') +
          (s.score === pick && sigs.length > 1 ? '<span class="cnt">◂ counts</span>' : '') + '<span class="ss">' + esc(s.score) + '</span></div>' +
        (s.parts || []).map(function (p) { return '<div class="pt"><span class="d' + (p.delta < 0 ? ' neg' : '') + '">' + delta(p.delta) + '</span><span>' + esc(p.text) + '</span></div>'; }).join('') +
        '<a class="sf" href="../' + esc(s.file) + '" target="_blank" rel="noopener">' + esc(base(s.file)) + ' ↗</a></div>';
    }).join('') || '<div class="sgl"><div class="sgh"><span>no check backs it</span><span class="ss">' + esc(x.score) + '</span></div></div>';
    if (con.length) body += '<div class="sgl con"><div class="sgh"><span>✕ contradicted</span>' + (F.contradicted_cap != null ? '<span class="ss">≤ ' + F.contradicted_cap + '</span>' : '') + '</div>' +
      con.map(function (c) { return '<p>' + rich(plain(c.summary)) + ' <a class="sf" href="../' + esc(c.file) + '" target="_blank" rel="noopener">' + esc(base(c.file)) + ' ↗</a></p>'; }).join('') + '</div>';
    body += '<div class="tot"><span class="sn">= ' + esc(x.score) + '</span><span class="bd">' + esc(x.band) + '</span><span class="fine">' + esc(x.how || '') + '</span></div>';
    if (dep.length) body += '<div class="rel"><span class="fine">depends on</span> ' + dep.map(goto).join(' ') + '</div>';
    if (sh.length) body += '<div class="rel"><span class="fine">shares lines with</span><ul>' + sh.map(function (t) { return '<li>' + rich(plain(t)) + '</li>'; }).join('') + '</ul></div>';
    return '<details class="rcpt"><summary>how the score adds up <span class="tw" aria-hidden="true">▸</span></summary><div class="paper">' + body + '</div></details>';
  }

  /* ---------- new tests ---------- */
  function testRuns(c) {
    var o = { before: null, after: null, extra: [] };
    (c.results || []).forEach(function (r) {
      var run = lc(r.run);
      if (!o.before && /^before/.test(run)) o.before = r;
      else if (!o.after && run === 'after the change') o.after = r;
      else o.extra.push(r);
    });
    return o;
  }
  function testKind(c) {
    var r = testRuns(c), v = lc(c.verdict);
    if (c.flips) return 'flip';
    if (/did not run/.test(v) || (r.after && r.after.outcome === 'build_failed')) return 'norun';
    if (/passes before/.test(v) || (r.before && r.before.outcome === 'pass')) return 'weak';
    return 'other';
  }
  function runWho(r, which) {
    if (which === 'before') return 'Old code';
    if (which === 'after') return 'New code';
    return /undone|revert/.test(lc(r.run)) ? 'New code with the fix undone' : plain(r.run);
  }
  /* "Old code: fails · New code: passes" */
  function runLine(c) {
    var r = testRuns(c), out = [];
    if (r.before) out.push([r.before, 'before']);
    if (r.after) out.push([r.after, 'after']);
    r.extra.forEach(function (x) { out.push([x, 'extra']); });
    return out.map(function (p) {
      var o = p[0].outcome;
      return '<span class="oc o-' + esc(String(o).replace(/_/g, '-')) + '">' + esc(runWho(p[0], p[1])) + ': <b>' + esc(OUT[o] || o) + '</b></span>';
    }).join('<span class="dot" aria-hidden="true"> · </span>');
  }
  function stepHtml(c, s) {
    var ln = s.lines || [], probs = s.problems || [];
    var where = ln.length ? 'lines ' + ln[0] + (ln[1] !== ln[0] ? '–' + ln[1] : '') : 'no lines cited';
    return '<li class="step op-' + esc(lc(s.op)) + (s.verified === false ? ' unv' : '') + '" tabindex="0" role="button" aria-pressed="false" title="' + esc(where) + '"' +
        ' data-f="' + esc(s.file || c.file) + '" data-s="' + (s.side === 'old' ? 'o' : 'n') + '" data-a="' + esc(ln[0]) + '" data-b="' + esc(ln[1] == null ? ln[0] : ln[1]) + '">' +
      '<span class="op">' + esc(s.op) + '</span><span class="sx">' + rich(s.text) + (s.in_change === false ? ' <span class="ctx" title="These lines are around the change, not part of it">nearby code</span>' : '') + '</span>' +
      (s.verified === false ? '<span class="unv-m"><b>? unverified</b>' + probs.map(function (p) { return ' ' + rich(p); }).join(' ·') + '</span>' : '') +
    '</li>';
  }
  function codeGroups(c) {
    var code = c.code || {}, used = {};
    var gs = [{ kind: 'test', name: c.test, file: c.file, span: c.span }].concat((c.helpers || []).map(function (h) {
      return { kind: 'helper', name: h.name, file: h.file, span: h.span };
    }));
    function nums(f) { return Object.keys(code[f] || {}).map(Number).sort(function (a, b) { return a - b; }); }
    gs.forEach(function (g) {
      var sp = g.span || [];
      g.lines = nums(g.file).filter(function (n) { return sp.length < 2 || (n >= sp[0] && n <= sp[1]); });
      g.lines.forEach(function (n) { used[g.file + '#' + n] = 1; });
    });
    Object.keys(code).forEach(function (f) {
      var rest = nums(f).filter(function (n) { return !used[f + '#' + n]; });
      if (rest.length) gs.push({ kind: 'lines', name: base(f), file: f, lines: rest });
    });
    return gs.filter(function (g) { return g.lines.length; }).map(function (g) {
      var src = code[g.file], prev = null;
      var ind = g.lines.reduce(function (m, n) { var t = src[n]; return t.trim() ? Math.min(m, t.match(/^[ \t]*/)[0].length) : m; }, 1e9);
      if (ind === 1e9) ind = 0;
      var rows = g.lines.map(function (n) {
        var gap = prev != null && n !== prev + 1 ? '<div class="r gap"><i>⋯</i></div>' : '';
        prev = n;
        return gap + '<div class="r" data-n="' + n + '"><i>' + n + '</i><span>' + esc(src[n].slice(ind)) + '</span></div>';
      }).join('');
      return '<div class="cg"><div class="cgh">' + g.kind + ' <b>' + esc(g.name) + '</b>' + (g.kind !== 'lines' ? ' <span>' + esc(base(g.file)) + '</span>' : '') + '</div>' +
        '<div class="cl" data-f="' + esc(g.file) + '">' + rows + '</div></div>';
    }).join('');
  }
  function analysisPane(c, k) {
    var dnc = c.does_not_check || [], notes = c.notes || [];
    var msgs = (c.results || []).filter(function (r) { return r.message; });
    var more = notes.map(function (n) { return '<p>' + rich(plain(n)) + '</p>'; }).join('') +
      (msgs.length ? '<ul class="msgs">' + msgs.map(function (r) { return '<li><span class="fine">' + esc(plain(r.run)) + '</span><code>' + esc(r.message) + '</code></li>'; }).join('') + '</ul>' : '') +
      ((c.claims || []).length ? '<p class="cl-l"><span class="fine">claims</span> ' + c.claims.map(goto).join(' ') + '</p>' : '');
    return '<div class="pane an"><h5>Why</h5>' +
      '<p class="verdict">' + (TK[k].say ? esc(TK[k].say) : rich(c.verdict || '')) + '</p>' +
      '<p class="runs">' + runLine(c) + '</p>' +
      (dnc.length ? '<div class="dnc"><h6>Doesn\u2019t check</h6><ul>' + dnc.map(function (x) { return '<li>' + rich(x) + '</li>'; }).join('') + '</ul></div>' : '') +
      (more ? '<details class="more"><summary>notes &amp; claims <span class="tw" aria-hidden="true">▸</span></summary>' + more + '</details>' : '') +
    '</div>';
  }
  function testCard(c) {
    var k = testKind(c), t = TK[k];
    return '<details class="tc k-' + k + '" id="test-' + esc(c.id) + '"' + (k === 'flip' ? ' open' : '') + '>' +
      '<summary><span class="tg" aria-hidden="true">' + t.g + '</span><span class="tname" title="' + esc(c.test) + '">' + esc(c.title || c.test) + '</span>' +
        '<span class="say">' + esc(k === 'other' ? c.verdict || t.row : t.row) + '</span><span class="tw" aria-hidden="true">▸</span></summary>' +
      '<p class="meth">test method <code>' + esc(c.test) + '</code> in ' + esc(base(c.file)) + '</p>' +
      '<div class="panes">' +
        '<div class="pane ps"><h5>What the test does</h5><ol class="steps">' + (c.steps || []).map(function (s) { return stepHtml(c, s); }).join('') + '</ol></div>' +
        '<div class="pane rc"><h5>The code</h5><div class="code" tabindex="0" aria-label="Code of ' + esc(c.test) + '">' + codeGroups(c) + '</div></div>' +
        analysisPane(c, k) +
      '</div></details>';
  }
  function testsSection(d) {
    var cards = ((d._tests || {}).details || {}).cards || [];
    if (!cards.length) return '';
    var n = { flip: 0, weak: 0, norun: 0, other: 0 };
    cards.forEach(function (c) { n[testKind(c)]++; });
    return '<section class="tests" aria-label="New tests">' +
      '<div class="sec-h"><span class="inv">NEW TESTS</span><span class="rule"></span></div>' +
      '<div class="tstrip"><span class="tall"><b>' + cards.length + '</b> test' + (cards.length === 1 ? '' : 's') + '</span>' +
        ['flip', 'weak', 'norun', 'other'].filter(function (k) { return n[k]; }).map(function (k) {
          return '<span class="k-' + k + '"><i aria-hidden="true">' + TK[k].g + '</i><b>' + n[k] + '</b> ' + (n[k] === 1 ? TK[k].one : TK[k].many) + '</span>';
        }).join('') + '</div>' +
      cards.map(testCard).join('') + '</section>';
  }
  function wireTests(root) {
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    root.querySelectorAll('.tc, .dc').forEach(function (card) {
      var pane = card.querySelector('.code'), pinned = null;
      if (!pane) return;
      function show(st) {
        pane.querySelectorAll('.r.hl').forEach(function (r) { r.classList.remove('hl'); });
        card.querySelectorAll('.step.on').forEach(function (s) { s.classList.remove('on'); });
        if (!st) return;
        st.classList.add('on');
        var a = +st.dataset.a, b = +st.dataset.b, hit = [];
        pane.querySelectorAll('.cl').forEach(function (cl) {
          if (cl.dataset.f !== st.dataset.f) return;
          var key = st.dataset.s || 'n';
          cl.querySelectorAll('.r[data-' + key + ']').forEach(function (r) {
            var x = +r.dataset[key];
            if (x >= a && x <= b) { r.classList.add('hl'); hit.push(r); }
          });
        });
        if (!hit.length) return;
        var pr = pane.getBoundingClientRect(), top = hit[0].getBoundingClientRect().top - pr.top, bot = hit[hit.length - 1].getBoundingClientRect().bottom - pr.top;
        if (top < 0 || bot > pane.clientHeight) pane.scrollTo({ top: pane.scrollTop + top - 28, behavior: reduce ? 'auto' : 'smooth' });
      }
      card.querySelectorAll('.step').forEach(function (st) {
        st.addEventListener('mouseenter', function () { show(st); });
        st.addEventListener('mouseleave', function () { show(pinned); });
        st.addEventListener('focus', function () { show(st); });
        st.addEventListener('blur', function () { show(pinned); });
        function toggle() {
          if (pinned) { pinned.classList.remove('pin'); pinned.setAttribute('aria-pressed', 'false'); }
          pinned = pinned === st ? null : st;
          if (pinned) { st.classList.add('pin'); st.setAttribute('aria-pressed', 'true'); }
          show(pinned || st);
        }
        st.addEventListener('click', toggle);
        st.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
      });
    });
  }

  /* ---------- AI decisions, each with pseudo-code, the real code and the reasons ---------- */
  function decCards(d) { return ((d._decisions || {}).details || {}).cards || []; }
  function decOf(d, id) { return decCards(d).filter(function (c) { return c.id === id; })[0] || null; }
  function diffCode(card) {
    return (card.code || []).map(function (g) {
      var ind = g.rows.reduce(function (m, r) { return r[0] !== 'gap' && r[3].trim() ? Math.min(m, r[3].match(/^[ \t]*/)[0].length) : m; }, 1e9);
      if (ind === 1e9) ind = 0;
      var rows = g.rows.map(function (r) {
        if (r[0] === 'gap') return '<div class="r gap"><i>⋯</i></div>';
        var cls = r[0] === '+' ? ' add' : r[0] === '-' ? ' del' : '';
        return '<div class="r' + cls + '"' + (r[1] != null ? ' data-o="' + r[1] + '"' : '') + (r[2] != null ? ' data-n="' + r[2] + '"' : '') + '>' +
          '<i>' + (r[2] != null ? r[2] : r[1]) + '</i><u aria-hidden="true">' + (r[0] === '+' ? '+' : r[0] === '-' ? '−' : '') + '</u><span>' + esc(r[3].slice(ind)) + '</span></div>';
      }).join('');
      return '<div class="cg"><div class="cgh"><b>' + esc(base(g.file)) + '</b><span class="lg"><em class="lg-del">− old</em> <em class="lg-add">+ new</em></span></div>' +
        '<div class="cl" data-f="' + esc(g.file) + '">' + rows + (g.cut ? '<div class="r gap"><i>⋯</i><span> ' + g.cut + ' more lines</span></div>' : '') + '</div></div>';
    }).join('');
  }
  var EVW = { pass: 'check passed', fail: 'check found a problem', error: 'check incomplete', missing: 'file missing' };
  function becauseHtml(b) {
    var r = lc(b.result);
    var chip = b.evidence ? '<a class="evc r-' + esc(r || 'none') + '" href="../' + esc(b.evidence) + '" target="_blank" rel="noopener" title="' + esc(plain(b.summary || '')) + '">' +
      esc(EVW[r] || r || 'evidence') + (b.produced_by === 'hand' ? ' · by hand' : '') + ' ↗</a>' : '';
    return '<li><span>' + rich(b.text) + '</span>' + chip + '</li>';
  }
  function decisionPanes(card) {
    var bad = (card.steps || []).filter(function (s) { return !s.verified; }).length;
    var n = (card.steps || []).length;
    return '<div class="panes dpanes">' +
      '<div class="pane ps"><h5>What the code does</h5><ol class="steps">' + (card.steps || []).map(function (s) { return stepHtml(card, s); }).join('') + '</ol>' +
        '<p class="chk' + (bad ? ' bad' : '') + '">' + (bad ? '? ' + bad + ' of ' + n + ' steps don’t match the code' : '✓ every step matches the code') + '</p></div>' +
      '<div class="pane rc"><h5>The code</h5><div class="code" tabindex="0" aria-label="Code for ' + esc(card.title) + '">' + diffCode(card) + '</div></div>' +
      '<div class="pane an"><h5>Why</h5><p class="verdict">' + rich(card.verdict) + '</p>' +
        ((card.because || []).length ? '<ul class="bc">' + card.because.map(becauseHtml).join('') + '</ul>' : '') +
        (card.impact ? '<div class="imp imp-' + esc(card.impact.level) + '"><h6>If this ships <em>' + esc(card.impact.level) + ' impact</em></h6>' +
          '<p><b>Who:</b> ' + rich(card.impact.who) + '</p><p><b>What happens:</b> ' + rich(card.impact.effect) + '</p></div>' : '') +
        (card.unsure ? '<div class="dnc"><h6>Not sure</h6><p>' + rich(card.unsure) + '</p></div>' : '') +
        (card.ask ? '<div class="ask"><h6>Your call</h6><p>' + rich(card.ask) + '</p></div>' : '') +
      '</div></div>';
  }
  /* the dossier's own wording, the requirement and the raw files, folded away */
  function filesBlock(d, c) {
    var out = '<p class="aiw"><span class="fine">The AI’s words</span> ' + rich(c.claim) + '</p>';
    if (c.requirement) {
      var rt = (d._requirements || {})[c.requirement];
      out += '<p class="aiw"><span class="fine">What the issue asks' + (c.requirement_inferred ? ' (our reading)' : '') + '</span> ' + (rt ? rich(rt) : esc(c.requirement)) + '</p>';
    }
    out += '<ul class="files">' + (c.evidence || []).map(function (ref) {
      var ev = (d._evidence || {})[ref], r = ev ? lc(ev.result) : 'missing';
      return '<li><a href="../' + esc(ref) + '" target="_blank" rel="noopener">' + esc(base(ref).replace(/\.json$/, '').replace(/[-_.]+/g, ' ')) + ' ↗</a>' +
        '<span class="evc r-' + esc(r) + '">' + esc(EVW[r] || r) + '</span>' + (ev && ev.summary ? '<span class="fs">' + rich(plain(ev.summary)) + '</span>' : '') + '</li>';
    }).join('') + '</ul>';
    return '<details class="more fb"><summary>full wording &amp; files <span class="tw" aria-hidden="true">▸</span></summary>' + out + '</details>';
  }
  var DK = { found: { g: '◆', w: 'found' }, drift: { g: '↗', w: 'not asked for' } };
  function findingsSection(d) {
    var cs = decCards(d).filter(function (c) { return c.kind === 'found' || c.kind === 'drift'; });
    if (!cs.length) return '';
    return '<div class="sec-h"><span class="inv">ALSO FOUND</span><span class="rule"></span><span class="dim">' + cs.length + '</span></div>' +
      '<p class="sec-g">Things the reviewer noticed beyond the claims.</p>' +
      cs.map(function (c) {
        var k = DK[c.kind];
        return '<details class="tc dc k-' + c.kind + '" id="row-' + esc(c.id) + '"><summary><span class="tg" aria-hidden="true">' + k.g + '</span>' +
          '<span class="tname">' + esc(c.title) + '</span><span class="say">' + k.w + '</span><span class="tw" aria-hidden="true">▸</span></summary>' +
          decisionPanes(c) + '</details>';
      }).join('');
  }

  /* ---------- readability ---------- */
  /* the learned rules (context/history.json); the page reads rule text from here, so an edit shows everywhere */
  function rulesDoc() { return ((window.PROJECT || {}).history) || { rules: [] }; }
  function ruleById(id) { return (rulesDoc().rules || []).filter(function (r) { return r.id === id; })[0] || null; }
  function readabilitySection(d) {
    var fl = ((d._readability || {}).details || {}).flags || [];
    if (!fl.length) return '';
    return '<div class="sec-h"><span class="inv">READABILITY</span><span class="rule"></span><span class="dim">' + fl.length + '</span></div>' +
      '<p class="sec-g">Flags tied to a maintainer rule. A tool measured each one; the AI traced what it means. <a href="#/rules">See or edit the rules ↗</a></p>' +
      fl.map(function (f) {
        var r = ruleById(f.rule), card = decOf(d, f.id);
        var text = r ? r.rule : (f.rule_text || ''), src = r ? r.sources : f.sources;
        var file = base(String(f.where || '').split(/[:;]/)[0]);
        var meas = String(f.measure || '').replace(/\s*\(.*\)\s*$/, '');
        return '<details class="tc dc k-flag" id="row-' + esc(f.id) + '"><summary><span class="tg" aria-hidden="true">≋</span>' +
            '<span class="tname">' + esc(card ? card.title : meas + (file ? ' · ' + file : '')) + '</span>' +
            '<span class="say">' + esc(f.rule) + ' · ' + esc(f.value_base) + ' → ' + esc(f.value_branch) + '</span><span class="tw" aria-hidden="true">▸</span></summary>' +
          '<div class="rdh">' +
            '<p class="rdr">' + ruleLink(f.rule, src) + ' ' + esc(text) + (r && r.edits && r.edits.length ? ' <span class="ed">edited by ' + esc(r.edits[r.edits.length - 1].who) + '</span>' : '') + (r ? '' : ' <span class="ed">rule no longer in the rules file</span>') + '</p>' +
            '<p class="rdm"><b>Measured:</b> ' + esc(f.measure) + ': ' + esc(f.value_base) + ' before, ' + esc(f.value_branch) + ' after.' + (f.detail ? ' ' + esc(f.detail) + '.' : '') + '</p>' +
            ((f.claims || []).length ? '<p class="rdc">Touches ' + f.claims.map(goto).join(' ') + '</p>' : '') +
          '</div>' +
          (card ? decisionPanes(card) : '<p class="rdm">No trace yet: <code>' + esc(f.where || '') + '</code></p>') +
        '</details>';
      }).join('');
  }

  /* ---------- learned rules: read and edit context/history.json ---------- */
  var CONCERNS = ['compat-breaking', 'public-api', 'wire-format', 'generated', 'diagnostics', 'targets', 'security',
    'user-docs', 'maintainability', 'readability', 'performance', 'tests', 'scope', 'other'];
  var rulesState = null;
  function quotesByUrl() {
    var m = {};
    ((rulesDoc().prs) || []).forEach(function (p) {
      (p.statements || []).forEach(function (st) { if (st.url) m[st.url] = { who: st.who, quote: st.quote, date: st.date, pr: p.pr, title: p.title }; });
    });
    return m;
  }
  /* which flags and owner gates cite each rule, across the dossiers */
  function ruleUses() {
    var u = {};
    keys().forEach(function (k) {
      var d = DATA[k];
      (((d._readability || {}).details || {}).flags || []).forEach(function (f) { (u[f.rule] = u[f.rule] || []).push({ k: k, id: f.id }); });
      var cl = ((d._confidence || {}).details || {}).claims || {};
      Object.keys(cl).forEach(function (cid) {
        ((cl[cid].gate || {}).rules || []).forEach(function (r) { (u[r.id] = u[r.id] || []).push({ k: k, id: cid }); });
      });
    });
    return u;
  }
  function rulesFromDoc() {
    return (rulesDoc().rules || []).map(function (r) {
      return { id: r.id, concern: r.concern, rule: r.rule, sources: (r.sources || []).slice(), off: !!r.off,
        times_cited: r.times_cited, edits: r.edits || [], added_by: r.added_by || null, isNew: false };
    });
  }
  function rulesDirty() {
    var orig = {};
    (rulesDoc().rules || []).forEach(function (r) { orig[r.id] = r; });
    return rulesState.rules.some(function (r) {
      var o = orig[r.id];
      return !o || o.rule !== r.rule || o.concern !== r.concern || !!o.off !== r.off || (o.sources || []).join('\n') !== r.sources.join('\n');
    });
  }
  function ruleCard(r, i, Q, U) {
    var uses = U[r.id] || [];
    var src = r.sources.map(function (u) {
      var q = Q[u];
      return '<li><a href="' + esc(u) + '" target="_blank" rel="noopener">' + (q ? esc(q.who) + ', PR ' + esc(q.pr) + ', ' + esc(q.date) : esc(u.replace(/^https:\/\/github\.com\//, ''))) + ' ↗</a>' +
        (q ? '<q>' + esc(q.quote) + '</q>' : '') + '</li>';
    }).join('');
    var last = r.edits.length ? r.edits[r.edits.length - 1] : null;
    return '<li class="lr' + (r.off ? ' off' : '') + '" data-i="' + i + '">' +
      '<div class="lr-h"><b class="lr-id">' + esc(r.id) + '</b>' +
        '<label class="lr-c"><span class="sr">Concern</span><select data-f="concern">' + CONCERNS.map(function (c) {
          return '<option' + (c === r.concern ? ' selected' : '') + '>' + esc(c) + '</option>'; }).join('') + '</select></label>' +
        '<label class="lr-on"><input type="checkbox" data-f="on"' + (r.off ? '' : ' checked') + '> in use</label>' +
        '<span class="lr-meta">' + (r.isNew ? 'new' : (r.added_by ? 'added by ' + esc(r.added_by.who) : 'learned from history') +
          (last ? ' · edited by ' + esc(last.who) + ' ' + esc(String(last.when).slice(0, 10)) : '')) + '</span></div>' +
      '<label class="sr" for="lr-t-' + i + '">Rule ' + esc(r.id) + '</label>' +
      '<textarea id="lr-t-' + i + '" data-f="rule" rows="2">' + esc(r.rule) + '</textarea>' +
      (src ? '<ul class="lr-src">' + src + '</ul>' : '<p class="lr-none">No maintainer quote backs this rule yet. Add a link below.</p>') +
      '<details class="lr-more"><summary>Edit links' + (uses.length ? ' · cited by ' + uses.length : '') + '</summary>' +
        '<label>Links to where a maintainer said it, one per line<textarea data-f="sources" rows="' + Math.max(2, r.sources.length) + '">' + esc(r.sources.join('\n')) + '</textarea></label>' +
        (uses.length ? '<p class="lr-uses">Cited by ' + uses.map(function (x) { return '<a href="#/d/' + encodeURIComponent(x.k) + '">' + esc(x.id) + '</a>'; }).join(', ') + '</p>' : '') +
      '</details>' +
    '</li>';
  }
  function renderRules() {
    state.key = null;
    mastRight.innerHTML = '<a href="#/" style="text-decoration:none">↩ dossiers</a>';
    if (!rulesState) rulesState = { rules: rulesFromDoc(), msg: '', bad: false };
    var doc = rulesDoc(), Q = quotesByUrl(), U = ruleUses();
    var on = rulesState.rules.filter(function (r) { return !r.off; }).length;
    app.innerHTML = '<section class="lrdoc">' +
      '<header class="lrdoc-h"><p class="eyebrow">context/history.json</p><h1>Learned rules</h1>' +
        '<p class="lede">' + esc(doc.summary || '') + ' Each rule says what the maintainers expect, with links to where they said it. ' +
        'The owner gate and the readability flags cite these rules. You can reword a rule, change its concern, turn it off, or add one.</p>' +
        '<p class="lrdoc-n">' + on + ' of ' + rulesState.rules.length + ' rules in use</p></header>' +
      '<ol class="lrs">' + rulesState.rules.map(function (r, i) { return ruleCard(r, i, Q, U); }).join('') + '</ol>' +
      '<div class="lrdoc-bar"><button type="button" class="lr-add">+ Add a rule</button>' +
        '<label class="lr-who">Your name <input id="lr-who" autocomplete="name" value="' + esc(store('et:name') || '') + '"></label>' +
        '<button type="button" class="lr-save">Save</button><button type="button" class="lr-reset">Undo changes</button>' +
        '<p class="lr-msg' + (rulesState.bad ? ' bad' : '') + '" role="status">' + esc(rulesState.msg) + '</p></div>' +
      '<p class="lrdoc-foot">Saving with <code>npm run dev</code> writes the file, records your name on each changed rule, and re-scores the dossiers. ' +
        'Without it, Save downloads the edited file: put it at <code>review/context/history.json</code> and run <code>npm run render</code>. Rules are never deleted, only turned off, so old evidence that cites them still makes sense.</p>' +
    '</section>';
    refreshRulesBar();
  }
  function refreshRulesBar() {
    var dirty = rulesDirty(), b = app.querySelector('.lr-save');
    if (b) { b.disabled = !dirty; b.textContent = dirty ? 'Save' : 'Saved'; }
    var r = app.querySelector('.lr-reset');
    if (r) r.disabled = !dirty;
  }
  function payloadRules() {
    return rulesState.rules.map(function (r) {
      return { id: r.id, concern: r.concern, rule: r.rule, sources: r.sources, off: r.off };
    });
  }
  function downloadRules(who) {
    var doc = JSON.parse(JSON.stringify(rulesDoc())), now = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
    var old = {};
    (doc.rules || []).forEach(function (r) { old[r.id] = r; });
    doc.rules = rulesState.rules.map(function (r) {
      var o = old[r.id];
      if (!o) return { id: r.id, concern: r.concern, rule: r.rule, sources: r.sources, times_cited: 0, added_by: { who: who, when: now } };
      var before = {};
      ['concern', 'rule', 'sources', 'off'].forEach(function (k) {
        var a = k === 'off' ? !!o.off : o[k], b = r[k];
        if (JSON.stringify(a) !== JSON.stringify(b)) before[k] = a;
      });
      if (!Object.keys(before).length) return o;
      var n = Object.assign({}, o, { concern: r.concern, rule: r.rule, sources: r.sources, edits: (o.edits || []).concat([{ who: who, when: now, before: before }]) });
      if (r.off) n.off = true; else delete n.off;
      return n;
    });
    var blob = new Blob([JSON.stringify(doc, null, 2) + '\n'], { type: 'application/json' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'history.json';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }
  function saveRules() {
    var who = (document.getElementById('lr-who') || {}).value || '';
    who = who.trim();
    if (!who) { rulesState.msg = 'Add your name first: each edit records who made it.'; rulesState.bad = true; renderRules(); return; }
    store('et:name', who);
    var empty = rulesState.rules.filter(function (r) { return !r.rule.trim(); })[0];
    if (empty) { rulesState.msg = empty.id + ' has no text.'; rulesState.bad = true; renderRules(); return; }
    rulesState.msg = 'Saving…'; rulesState.bad = false; renderRules();
    fetch('/api/rules', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ who: who, rules: payloadRules() }) })
      .then(function (res) {
        if (res.status === 404 || res.status === 405 || res.status === 501) throw { offline: true };
        return res.json().then(function (j) { if (!res.ok || !j.ok) throw { msg: j.error || (j.runs || []).filter(function (r) { return !r.ok; }).map(function (r) { return r.cmd + ' failed'; }).join('; ') || 'save failed' }; return j; });
      })
      .then(function (j) {
        rulesState = null;
        sessionStorage.setItem('et:rules-msg', j.summary + '. Scores re-computed.');
        location.reload();
      })
      .catch(function (e) {
        if (e && e.msg) { rulesState.msg = e.msg; rulesState.bad = true; renderRules(); return; }
        downloadRules(who);
        rulesState.msg = 'No dev server here, so the edited file was downloaded. Put it at review/context/history.json and run npm run render.';
        rulesState.bad = false; renderRules();
      });
  }
  app.addEventListener('input', function (e) {
    var li = e.target.closest && e.target.closest('.lr');
    if (!li || !rulesState) return;
    var r = rulesState.rules[+li.dataset.i], f = e.target.dataset.f;
    if (f === 'rule') r.rule = e.target.value;
    else if (f === 'concern') r.concern = e.target.value;
    else if (f === 'sources') r.sources = e.target.value.split('\n').map(function (x) { return x.trim(); }).filter(Boolean);
    else if (f === 'on') { r.off = !e.target.checked; li.classList.toggle('off', r.off); }
    rulesState.msg = ''; refreshRulesBar();
  });
  app.addEventListener('change', function (e) {
    if (e.target.dataset && (e.target.dataset.f === 'concern' || e.target.dataset.f === 'on')) e.target.dispatchEvent(new Event('input', { bubbles: true }));
  });
  app.addEventListener('click', function (e) {
    if (!rulesState || !e.target.closest) return;
    if (e.target.closest('.lr-save')) saveRules();
    else if (e.target.closest('.lr-reset')) { rulesState = null; renderRules(); }
    else if (e.target.closest('.lr-add')) {
      var max = rulesState.rules.reduce(function (m, r) { return Math.max(m, +String(r.id).slice(2) || 0); }, 0);
      var id = 'H-' + (max + 1 < 10 ? '0' : '') + (max + 1);
      rulesState.rules.push({ id: id, concern: 'other', rule: '', sources: [], off: false, edits: [], added_by: null, isNew: true });
      renderRules();
      var t = app.querySelector('.lr:last-child textarea');
      if (t) { t.scrollIntoView({ block: 'center' }); t.focus(); }
    }
  });

  function jumpTo(el) {
    if (!el) return;
    if (el.tagName === 'DETAILS') el.open = true;
    el.scrollIntoView({ block: 'start' });
    var f = el.tagName === 'DETAILS' ? el.querySelector('summary') : el.querySelector('input') || el;
    if (f) f.focus({ preventScroll: true });
  }
  app.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-goto]');
    if (!b) return;
    e.preventDefault();
    jumpTo(document.getElementById('row-' + b.dataset.goto));
  });

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

    var F = ((d._confidence || {}).details || {}).formula || {}, cut = F.bands || { high: 80, medium: 50 };
    var range = { high: cut.high + '+', medium: cut.medium + '–' + (cut.high - 1), low: 'under ' + cut.medium, owner: '' };
    var tiers = GROUPS.map(function (t, i) {
      return (i === 3 ? '<span class="sep" aria-hidden="true"></span>' : '') +
        '<button type="button" class="tier bn-' + t + (t === 'owner' ? ' owner' : '') + '" data-jump="' + t + '"' + (n[t] ? '' : ' disabled') + ' aria-label="' + n[t] + ' ' + BAND[t].w + '">' +
          '<span class="n' + (n[t] ? '' : ' zero') + '">' + n[t] + '</span>' +
          '<span class="nm"><span aria-hidden="true">' + BAND[t].g + '</span> ' + BAND[t].w + '</span>' +
          '<span class="bar"><b style="--p:' + (100 * n[t] / total).toFixed(1) + '%"></b></span>' +
          '<span class="gl">' + (range[t] ? '<b>' + esc(range[t]) + '</b> · ' : '') + esc(BAND[t].short) + '</span>' +
        '</button>';
    }).join('');

    var leds = human.map(function (c) { return '<span class="led" data-led="' + esc(c.id) + '"></span>'; }).join('');

    app.innerHTML =
      '<section class="dossier">' +
        '<aside class="side' + (store('et:rail') ? ' open' : '') + '" id="side">' +
          '<div class="rail">' +
            '<button type="button" class="rail-t" id="rail-t" aria-expanded="' + (store('et:rail') ? 'true' : 'false') + '" aria-controls="drawer" title="Issue details and signing">' +
              '<span class="rn">' + issueNo + '</span><span class="ra" aria-hidden="true">▸</span></button>' +
            '<div class="p-leds rail-leds" aria-hidden="true">' + leds + '</div>' +
            '<button type="button" class="rail-sign" id="rail-sign">sign</button>' +
          '</div>' +
          '<div class="drawer" id="drawer">' +
          '<button type="button" class="drawer-x" id="drawer-x" aria-label="Fold the sidebar">◂ fold</button>' +
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
              '<p class="p-sub">Signing records your decisions, every claim\u2019s score and what nobody checked, for commit ' + esc(d.head || '') + '.</p>' +
              '<div class="p-row">' +
                '<label class="sr" for="signer">Your name</label>' +
                '<input class="sigfield" id="signer" name="signer" placeholder="Your name" maxlength="80" spellcheck="false">' +
                '<button class="btn" id="sign" type="submit">Sign</button>' +
              '</div>' +
              '<span class="mouth" aria-hidden="true"></span>' +
              '<p class="p-status" id="sign-status" aria-live="polite"></p>' +
            '</form>' +
          '</div>' +
          '</div>' +
        '</aside>' +
        '<div class="monitor">' +
          '<div class="inset"><div class="crt">' +
            '<div class="flicker"></div><div class="sweep"></div>' +
            '<div class="term" id="term" tabindex="0" aria-label="Dossier">' +
              '<div class="t-top"><span class="inv">' + esc(d.branch) + '</span><span id="sigstate" class="dim">' + esc(d.head || '') + '</span></div>' +
              '<div class="tiers">' + tiers + '</div>' +
              (human.length ?
                '<div class="sec-h"><span class="inv" style="background:var(--t-refused)">NEEDS OWNER</span><span class="rule"></span><span id="pickcount"></span></div>' +
                '<p class="sec-g">Users would notice these changes. You decide: accept, reject, or send back to the AI.</p>' +
                human.map(function (c) { return ownerRow(d, c); }).join('') : '') +
              (machine.length ?
                '<div class="sec-h"><span class="inv">' + (human.length ? 'OTHER CHANGES' : 'CHANGES') + '</span><span class="rule"></span><span class="dim">' + machine.length + '</span></div>' +
                '<p class="sec-g">What the AI changed, best backed first. Open one to see the code and the proof.</p>' +
                '<div>' + machine.map(function (c) { return machineRow(d, c); }).join('') + '</div>' : '') +
              testsSection(d) +
              findingsSection(d) +
              readabilitySection(d) +
              '<div class="sec-h"><span class="inv">GAPS</span><span class="rule"></span></div>' +
              '<div class="lists">' +
                list('NOT CHECKED', 'What nobody verified.', d.not_checked, rich, true) +
                list('NO CLAIM', 'Changed code no claim explains.', d.uncovered_diff_parts, function (p) { return '<code>' + esc(p) + '</code>'; }, true, 'Every changed line is explained by a claim.') +
                (findingsSection(d) ? '' : list('FOUND', 'What the reviewer found.', d.found, rich) + list('SCOPE DRIFT', 'Changes the issue did not ask for.', d.scope_drift, rich, true)) +
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
        jumpTo(app.querySelector('[data-band="' + b.dataset.jump + '"]'));
      });
    });
    var side = document.getElementById('side');
    function setRail(open, focus) {
      side.classList.toggle('open', open);
      document.getElementById('rail-t').setAttribute('aria-expanded', open ? 'true' : 'false');
      store('et:rail', open ? 1 : 0);
      if (open && focus) focus.focus();
    }
    document.getElementById('rail-t').addEventListener('click', function () { setRail(!side.classList.contains('open'), document.getElementById('drawer-x')); });
    document.getElementById('drawer-x').addEventListener('click', function () { setRail(false, document.getElementById('rail-t')); });
    document.getElementById('rail-sign').addEventListener('click', function () { setRail(true, signer); });
    side.addEventListener('keydown', function (e) { if (e.key === 'Escape' && side.classList.contains('open')) setRail(false, document.getElementById('rail-t')); });
    wireTests(app);
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
      app.querySelectorAll('[data-led="' + CSS.escape(c.id) + '"]').forEach(function (led) { led.classList.toggle('on', !!state.picks[c.id]); });
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
    if (st && !state.receipt) st.textContent = picked < human.length ? (human.length === 1 ? 'Decide the claim to sign.' : 'Decide all ' + human.length + ' claims to sign (' + (human.length - picked) + ' left).') : (!ready ? 'Type your name to sign.' : 'Ready to sign.');
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

  function withScore(d, c, o) {
    var x = confOf(d, c);
    o.score = x.score; o.band = x.band;
    if (x.gate) o.owner = x.gate.owner || '';
    return o;
  }
  /* band and score for a receipt line; older receipts carry neither, so look them up */
  function slipGrade(p) {
    var x = p.band ? p : cf(DATA[state.key] || {}, p.id);
    return x ? (BAND[x.band] || {}).g + ' ' + String(x.band).toUpperCase() + ' ' + x.score : '';
  }
  function buildReceipt(d, name) {
    var human = humanOf(d);
    var r = {
      branch: d.branch,
      head: d.head,
      signed_by: name,
      signed_at: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
      picks: human.map(function (c) { return withScore(d, c, { id: c.id, pick: state.picks[c.id], claim: c.claim || '' }); }),
      auto_settled: machineOf(d).map(function (c) { return withScore(d, c, { id: c.id }); }),
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
          return '<div class="ln"><span>' + esc(p.id) + '</span><span class="sub">' + esc(slipGrade(p)) + '</span>' +
            '<span class="pk ' + esc(String(p.pick).replace(' ', '-')) + '">' + esc(String(p.pick).toUpperCase()) + '</span></div>' +
            '<div class="cl">' + esc(p.claim) + '</div>';
        }).join('') +
        '<hr class="rule">' +
        (auto.length ? '<div class="sub">OTHER CLAIMS</div><div class="auto">' + auto.map(function (a) {
          return '<span>' + esc(a.id) + ' <span class="sub">' + esc(slipGrade(a)) + '</span></span>';
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
    else if (h === 'rules') renderRules();
    else { state.key = null; renderLanding(); }
    window.scrollTo(0, 0);
    if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
    app.focus({ preventScroll: true });
    var d = m && DATA[m[1]];
    document.title = d ? (d.issue != null ? '#' + d.issue + ' · ' : '') + 'Earned Trust' : h === 'rules' ? 'Learned rules · Earned Trust' : 'Earned Trust';
    var saved = null;
    try { saved = sessionStorage.getItem('et:rules-msg'); sessionStorage.removeItem('et:rules-msg'); } catch (e) {}
    if (saved && h === 'rules' && rulesState) { rulesState.msg = saved; renderRules(); }
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
