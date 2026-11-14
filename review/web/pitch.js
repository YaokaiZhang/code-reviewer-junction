/* Earned Trust — the pitch: a scroll story below the landing hero.
   Plain JS. Every number comes from window.DOSSIERS at runtime. */
(function () {
  'use strict';

  var TIERS = ['Proved', 'Tested', 'Measured', 'Argued', 'Refused'];
  var MACHINE = { Proved: 1, Tested: 1, Measured: 1 };
  var GLYPH = { Proved: '■', Tested: '▲', Measured: '●', Argued: '◆', Refused: '✕' };
  /* one-line meaning of each tier (CONVENTIONS.md, "Tier rules") */
  var DEF = {
    Proved: 'A checker rebuilt the output from the code, and it matched exactly.',
    Tested: 'A new test fails before the change and passes after it.',
    Measured: 'A tool counted it. The number is the evidence.',
    Argued: 'No check can settle it. It rests on reasoning.',
    Refused: 'Public API, warnings or security: off-limits for machines.'
  };
  var SHORT = {
    Proved: 'rebuilt and matched',
    Tested: 'a test fails before, passes after',
    Measured: 'a tool counted it',
    Argued: 'no check settles it',
    Refused: 'off-limits for machines'
  };
  /* one short example claim per tier, in plain words (the full claim is in its dossier) */
  var EXAMPLE = {
    Proved: ['C-2297-02', 'Every changed test snapshot is exactly what the new code generates.'],
    Tested: ['C-2283-01', 'The crash on generic structs from another project is fixed.'],
    Measured: ['C-2234-06', 'The fix adds copy-pasted code.'],
    Argued: ['C-2234-08', 'Types that skip code generation still serialise correctly.'],
    Refused: ['C-2283-02', 'A new filter hides some warnings from developers.']
  };
  /* plain glosses for analyzer codes that appear in claim text */
  var GLOSS = { MsgPack003: 'a build warning', MsgPack005: 'a build error' };
  var CHAPTERS = [
    { id: 'ch-problem', n: '01', title: 'The problem' },
    { id: 'ch-built', n: '02', title: 'What we built' },
    { id: 'ch-machine', n: '03', title: 'Machines settle' },
    { id: 'ch-owner', n: '04', title: 'Owners decide' },
    { id: 'ch-know', n: '05', title: 'How we know' }
  ];

  var cleanup = [];
  var progressFns = [];
  var raf = 0;
  var reduce = false;

  /* ---------- helpers ---------- */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  /* claim text: `code` spans, and a plain gloss after the first analyzer code */
  function rich(s) {
    var seen = {};
    return esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/MsgPack\d{3}/g, function (m) {
      if (seen[m] || !GLOSS[m]) return m;
      seen[m] = 1;
      return m + ' <span class="p-gloss">(' + GLOSS[m] + ')</span>';
    });
  }
  function lc(s) { return String(s || '').toLowerCase(); }
  function fmt(n) { return Math.round(n).toLocaleString('en-US'); }
  function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
  function claims(d) { return Array.isArray(d.claims) ? d.claims : []; }
  function on(t, ev, fn, opt) { t.addEventListener(ev, fn, opt); cleanup.push(function () { t.removeEventListener(ev, fn, opt); }); }
  function shortCmd(c) {
    return String(c || '').replace(/^cd \S+ && /, '').replace(/\/(?:tmp|home|root)\/\S*?\/(review\/)/g, '$1');
  }
  function issueOf(d) { return d.issue != null ? d.issue : String(d.branch || '').replace(/\D+/g, ''); }
  function plural(n, one, many) { return fmt(n) + ' ' + (n === 1 ? one : (many || one + 's')); }

  /* claim-coverage evidence, wherever the renderer put it */
  function coverageOf(d) {
    if (d._coverage && d._coverage.details) return d._coverage;
    var ev = d._evidence || {}, k = Object.keys(ev).filter(function (p) { return ev[p] && ev[p].check === 'claim-coverage'; })[0];
    return k ? ev[k] : null;
  }
  function evByCheck(d, check) {
    var ev = d._evidence || {};
    var k = Object.keys(ev).filter(function (p) { return ev[p] && ev[p].check === check; })[0];
    return k ? ev[k] : null;
  }

  /* ---------- the numbers ---------- */
  function stats(DATA) {
    var ds = Object.keys(DATA).sort().map(function (k) { var d = DATA[k]; d.__key = k; return d; })
      .filter(function (d) { return !d.sample; });
    var s = {
      ds: ds, lines: 0, files: 0, claims: 0, tiers: {}, byTier: {}, evidence: {}, script: 0, hand: 0,
      hunks: 0, hunksSeen: 0, uncovered: 0, notChecked: 0, notCheckedList: [], commands: [], open: 0, receipts: 0,
      snap: null
    };
    TIERS.forEach(function (t) { s.tiers[t] = 0; s.byTier[t] = []; });
    ds.forEach(function (d) {
      var df = d.diff || {};
      s.lines += (+df.insertions || 0) + (+df.deletions || 0);
      s.files += +df.files || 0;
      (d.not_checked || []).forEach(function (t) { s.notChecked++; s.notCheckedList.push({ t: t, d: d }); });
      s.uncovered += (d.uncovered_diff_parts || []).length;
      if (d._receipt) s.receipts++;
      claims(d).forEach(function (c) {
        s.claims++;
        if (s.tiers[c.tier] != null) { s.tiers[c.tier]++; s.byTier[c.tier].push({ c: c, d: d }); }
        if (!MACHINE[c.tier]) s.open++;
      });
      var ev = d._evidence || {};
      Object.keys(ev).forEach(function (p) {
        var e = ev[p]; if (!e || s.evidence[p]) return;
        s.evidence[p] = e;
        if (e.produced_by === 'hand') s.hand++; else s.script++;
        if (e.command) s.commands.push(shortCmd(e.command));
      });
      var cv = coverageOf(d);
      if (cv) { s.hunks += +cv.details.hunks_total || 0; s.hunksSeen++; }
      /* how many changed lines are generated snapshot files (diff classifier) */
      var dc = evByCheck(d, 'diff-classifier'), dt = dc && dc.details;
      if (dt && dt.insertions_by_category && dt.insertions_by_category.snapshot != null) {
        var n = (+dt.insertions_by_category.snapshot || 0) + (+((dt.deletions_by_category || {}).snapshot) || 0);
        var tot = (+dt.insertions || 0) + (+dt.deletions || 0);
        if (!s.snap || n > s.snap.n) s.snap = { n: n, files: +dt.snapshots_total || +(dt.counts_by_category || {}).snapshot || 0, of: tot, d: d };
      }
    });
    s.evidenceCount = s.script + s.hand;
    return s;
  }

  function evOf(item) {
    var ev = (item.d._evidence || {});
    return (item.c.evidence || []).map(function (p) { return ev[p]; }).filter(Boolean);
  }
  /* pick an example claim of a tier: prefer `want(item)`, avoid analyzer codes, then shortest */
  var JARGON = /MsgPack0\d\d|AD0001|CS\d{4}|\.tt\b|netstandard|TypeCollector/;
  function pick(s, tier, want, avoid) {
    var xs = s.byTier[tier].filter(function (it) { return !(avoid && avoid[it.c.id]); });
    if (!xs.length) xs = s.byTier[tier].slice();
    return xs.map(function (it) {
      return { it: it, k: (want && want(it) ? 0 : 1e4) + (JARGON.test(it.c.claim) ? 1e3 : 0) + it.c.claim.length };
    }).sort(function (a, b) { return a.k - b.k; }).map(function (x) { return x.it; })[0] || null;
  }
  function usesCheck(name) { return function (it) { return evOf(it).some(function (e) { return e.check === name; }); }; }

  /* ---------- pieces ---------- */
  function transition(text, hot, ch, ctx) {
    var ws = text.split(' ');
    var c = ch && CHAPTERS.filter(function (x) { return x.id === ch; })[0];
    return '<section class="p-trans"' + (c ? ' id="' + c.id + '" data-chapter="' + c.id + '"' : '') + ' data-progress="trans">' +
      '<div class="p-sticky p-trans-in">' +
        (c ? '<div class="p-chap"><span>' + c.n + '</span><i></i>' + esc(c.title) + '</div>' : '') +
        '<div class="p-line"></div><div class="p-dot"></div>' +
        '<p class="p-sentence">' + ws.map(function (w, i) {
          return '<span class="w' + (i >= ws.length - hot ? ' hot' : '') + '">' + esc(w) + ' </span>';
        }).join('') + '</p>' +
        (ctx ? '<p class="p-ctx p-trans-ctx">' + ctx + '</p>' : '') +
      '</div></section>';
  }
  function words(text, cls, delay) {
    return '<span class="p-words ' + (cls || '') + '" data-rv>' + text.split(' ').map(function (w, i) {
      return '<span class="wm"><span class="wi" style="transition-delay:' + ((delay || 0) + i * 70) + 'ms">' + esc(w) + '&nbsp;</span></span>';
    }).join('') + '</span>';
  }
  function strip(d) {
    var cs = claims(d).slice().sort(function (a, b) { return TIERS.indexOf(a.tier) - TIERS.indexOf(b.tier); });
    return '<span class="p-strip" aria-hidden="true">' + cs.map(function (c) {
      return '<i style="background:var(--t-' + lc(c.tier) + ')"' + (MACHINE[c.tier] ? '' : ' class="p-own"') + ' title="' + esc(c.tier) + '"></i>';
    }).join('') + '</span>';
  }

  /* ---------- sections ---------- */
  function secProblem(s) {
    var rows = s.ds.map(function (d) {
      var df = d.diff || {}, n = (+df.insertions || 0) + (+df.deletions || 0);
      return '<li><span class="b">#' + esc(issueOf(d)) + '</span>' +
        '<span class="bar"><i data-w="' + (100 * n / (s.lines || 1)).toFixed(2) + '"></i></span>' +
        '<span class="n">' + fmt(n) + '</span></li>';
    }).join('');
    var ribbon = '';
    for (var i = 0; i < 64; i++) {
      var w = 20 + ((i * 37) % 70);
      ribbon += '<i class="' + (i % 9 === 4 ? 'del' : 'add') + '" style="width:' + w + '%"></i>';
    }
    var hook = s.snap && s.snap.n ? '<p class="p-ctx p-hook" data-rv><b>' + fmt(s.snap.n) + '</b> of those lines are ' +
      (s.snap.files ? plural(s.snap.files, 'generated test snapshot file') : 'generated test snapshots') + ' in #' + esc(issueOf(s.snap.d)) +
      ' — too many to read, but a machine can regenerate them and compare.</p>' : '';
    return '<section class="p-sec p-problem">' +
      '<div class="p-grid2">' +
        '<div>' +
          '<div class="p-big" data-count="' + s.lines + '">0</div>' +
          '<h2 class="p-h2">' + words('lines changed.') + '<br>' + words('Who reads them?', 'hot', 160) + '</h2>' +
          '<ul class="p-bars" data-rv aria-label="Lines changed per branch">' + rows + '</ul>' +
          '<p class="p-cap">Lines changed per branch, named by its GitHub issue.</p>' +
          hook +
        '</div>' +
        '<div class="p-choice" data-rv>' +
          '<div class="p-ribbon" aria-hidden="true">' + ribbon + '</div>' +
          '<div class="p-keys">' +
            '<span class="p-key big">Approve</span>' +
            '<span class="p-key small">Read</span>' +
          '</div>' +
          '<p class="p-cap p-keycap">Today a reviewer has two buttons: approve without reading, or read every line.</p>' +
        '</div>' +
      '</div>' +
    '</section>';
  }

  function ladderExamples(s) {
    var ex = {};
    TIERS.forEach(function (t) {
      var id = EXAMPLE[t] && EXAMPLE[t][0];
      ex[t] = s.byTier[t].filter(function (it) { return it.c.id === id; })[0] || pick(s, t);
    });
    return ex;
  }

  function secLadder(s, used) {
    var ex = ladderExamples(s);
    var rows = TIERS.map(function (t, i) {
      return (i === 3 ? '<li class="split"><span>Machines settle the top three. People decide the bottom two.</span></li>' : '') +
        '<li class="p-rung c-' + lc(t) + '" data-i="' + i + '" style="--c:var(--t-' + lc(t) + ')">' +
          '<b aria-hidden="true">' + GLYPH[t] + '</b><span class="t">' + t + '<small>' + SHORT[t] + '</small></span><span class="n">' + s.tiers[t] + '</span></li>';
    }).join('');
    var cards = TIERS.map(function (t, i) {
      var it = ex[t], short = it && EXAMPLE[t] && EXAMPLE[t][0] === it.c.id ? EXAMPLE[t][1] : (it ? it.c.claim : '');
      return '<article class="p-card" data-i="' + i + '" style="--c:var(--t-' + lc(t) + ')">' +
        '<header><span class="g">' + GLYPH[t] + ' ' + t + '</span>' +
          '<span class="p-who">' + (MACHINE[t] ? 'machine settles' : 'person decides') + '</span></header>' +
        '<p class="p-def">' + esc(DEF[t]) + '</p>' +
        (it ? '<div class="p-ex"><span class="p-lbl">e.g. #' + esc(issueOf(it.d)) + '</span><p>“' + rich(short) + '”</p></div>' : '') +
      '</article>';
    }).join('');
    return '<section class="p-ladder" data-progress="ladder">' +
      '<div class="p-sticky p-ladder-in">' +
        '<div class="p-ladder-head"><span class="p-big p-sm" data-count="' + s.claims + '">0</span><span class="p-h3">claims, five tiers</span></div>' +
        '<p class="p-ctx p-ladder-ctx">Each claim gets the tier of the evidence behind it, strongest first.</p>' +
        '<div class="p-ladder-body">' +
          '<ol class="p-rungs">' + rows + '</ol>' +
          '<div class="p-cards">' + cards + '</div>' +
        '</div>' +
        '<div class="p-meter"><i></i></div>' +
      '</div></section>';
  }

  /* first evidence anywhere with this check (optionally on a given branch) */
  function findEv(s, check, branch) {
    for (var k in s.evidence) {
      var e = s.evidence[k];
      if (e && e.check === check && e.produced_by !== 'hand' && (!branch || k.indexOf(branch) >= 0)) return e;
    }
    return null;
  }
  function tool(e) {
    var m = e && e.command && e.command.match(/review\/scripts\/([\w\/.-]+\.py)/);
    return m ? m[1].replace(/\/run\.py$/, '') : '';
  }
  function squares(n, cls) {
    var o = ''; for (var i = 0; i < n; i++) o += '<i></i>';
    return '<span class="p-sq ' + (cls || '') + '">' + o + '</span>';
  }

  /* ch.03 — how a machine settles a claim, one diagram per tier */
  function secMachine(s) {
    var rows = [];
    var rg = findEv(s, 'regeneration'), runs = (rg && rg.details && rg.details.runs) || [];
    var br = runs.filter(function (r) { return r.label === 'branch'; })[0];
    var nSnap = (s.snap && s.snap.files) || 0;
    if (br && nSnap) rows.push({ t: 'Proved', h: 'Rebuild it. Compare.', e: rg,
      fig: '<div class="p-fig p-fig-proved">' +
        '<figure>' + squares(nSnap) + '<figcaption>' + fmt(nSnap) + ' files the agent committed</figcaption></figure>' +
        '<b class="p-eq">=</b>' +
        '<figure>' + squares(nSnap, 'regen') + '<figcaption>' + fmt(nSnap) + ' files rebuilt from the code</figcaption></figure>' +
        '<p class="p-out">✓ identical · ' + br.passed + ' of ' + br.total + ' tests pass</p></div>' });

    var ot = findEv(s, 'old-vs-new-tests', '2283') || findEv(s, 'old-vs-new-tests');
    var nT = ot && ot.details && ot.details.counts ? +ot.details.counts.evidence : 0;
    if (nT) {
      var cells = '';
      for (var i = 0; i < nT; i++) cells += '<span class="x">✗</span><span class="ok">✓</span>';
      rows.push({ t: 'Tested', h: 'Run the new tests on the old code.', e: ot,
        fig: '<div class="p-fig p-fig-tested"><div class="p-tgrid" style="--n:' + nT + '">' +
          '<span class="hd">before the fix</span><span class="hd">after</span>' + cells + '</div>' +
          '<p class="p-out">fails before, passes after</p></div>' });
    }

    var cc = findEv(s, 'clone-complexity'), cd = cc && cc.details;
    if (cd && cd.base && cd.branch) {
      var b0 = +cd.base.clones.duplicated_blocks, b1 = +cd.branch.clones.duplicated_blocks, mx = Math.max(b0, b1) || 1;
      rows.push({ t: 'Measured', h: 'Count it.', e: cc,
        fig: '<div class="p-fig p-fig-measured">' +
          '<div class="p-mbar"><span>before</span><i data-w="' + (100 * b0 / mx).toFixed(1) + '"></i><b>' + b0 + '</b></div>' +
          '<div class="p-mbar"><span>after</span><i data-w="' + (100 * b1 / mx).toFixed(1) + '"></i><b>' + b1 + '</b></div>' +
          '<p class="p-out">copy-pasted blocks in ' + esc(String(cd.file || '').split('/').pop()) + '</p></div>' });
    }

    var m = s.tiers.Proved + s.tiers.Tested + s.tiers.Measured;
    return '<section class="p-sec p-machine">' +
      '<h2 class="p-h2"><span class="p-num" data-count="' + m + '">0</span> ' + words('of ' + s.claims + ' settled') + '<br>' + words('by machine.', 'hot', 120) + '</h2>' +
      '<div class="p-hows">' + rows.map(function (r) {
        return '<article class="p-how" style="--c:var(--t-' + lc(r.t) + ')" data-rv>' +
          '<div class="p-how-t"><span class="g"><b aria-hidden="true">' + GLYPH[r.t] + '</b> ' + r.t + '</span>' +
            '<h3>' + esc(r.h) + '</h3>' +
            (tool(r.e) ? '<code class="p-tool">' + esc(tool(r.e)) + '</code>' : '') + '</div>' +
          r.fig + '</article>';
      }).join('') + '</div>' +
    '</section>';
  }

  function secOwner(s, used) {
    var rows = s.ds.map(function (d) {
      var a = 0, r = 0;
      claims(d).forEach(function (c) { if (c.tier === 'Argued') a++; if (c.tier === 'Refused') r++; });
      function g(n, t) { var o = ''; for (var i = 0; i < n; i++) o += '<b style="--c:var(--t-' + lc(t) + ');transition-delay:' + (i * 90) + 'ms" title="' + t + '">' + GLYPH[t] + '</b>'; return o; }
      return '<li data-rv><span class="b">#' + esc(issueOf(d)) + '</span><span class="g">' + g(a, 'Argued') + g(r, 'Refused') + '</span></li>';
    }).join('');
    /* the quote: an Argued claim that only the agent's word backs, if there is one */
    var aq = pick(s, 'Argued', function (it) { return /^Agent's claim/i.test(it.c.claim); });
    if (aq) used[aq.c.id] = 1;

    /* receipt: a real one if any dossier was signed; otherwise an empty, clearly unsigned form */
    var dr = s.ds.filter(function (d) { return d._receipt; })[0];
    var d0 = dr || s.ds.slice().sort(function (a, b) { return claims(a).length - claims(b).length; })[0];
    var rc = d0 && d0._receipt;
    var picks = d0 ? claims(d0).filter(function (c) { return !MACHINE[c.tier]; }) : [];
    var auto = d0 ? claims(d0).filter(function (c) { return MACHINE[c.tier]; }) : [];
    function shortClaim(c) {
      var w = String(c.claim || '').replace(/`/g, '').split(/\s+/);
      return w.slice(0, 6).join(' ') + (w.length > 6 ? '…' : '');
    }
    var opts = ['accept', 'send back', 'reject'];
    var slip = d0 ? '<div class="p-slip"><div class="p-slip-in">' +
      '<h4>RECEIPT</h4>' +
      (rc ? '' : '<div class="p-ex">EXAMPLE · NOT SIGNED</div>') +
      '<div class="c">#' + esc(issueOf(d0)) + ' at commit ' + esc(d0.head || '') + '</div><hr>' +
      '<div class="p-hd">Owner’s call on each open claim</div>' +
      picks.map(function (c) {
        var pk = rc ? ((rc.picks || []).filter(function (p) { return p.id === c.id; })[0] || {}).pick : null;
        return '<div class="ln"><span class="p-q">' + GLYPH[c.tier] + ' ' + esc(shortClaim(c)) + '</span>' +
          '<span class="p-opts">' + opts.map(function (o) {
            return '<span class="p-o' + (pk === o ? ' on' : '') + '"><i>' + (pk === o ? '✓' : '') + '</i>' + o + '</span>';
          }).join('') + '</span></div>';
      }).join('') + '<hr>' +
      '<div class="auto">Settled by machine: ' + plural(auto.length, 'claim') + ' ' + auto.map(function (c) { return GLYPH[c.tier]; }).join(' ') + '</div>' +
      '<div class="auto">Not checked: ' + plural((d0.not_checked || []).length, 'item') + ', listed</div><hr>' +
      '<div class="sig"><span>SIGNED</span>' + (rc ? '<em>' + esc(rc.signed_by) + '</em>' : '<span class="p-blank" aria-label="not signed"></span>') + '</div>' +
    '</div></div>' : '';
    var cap = '<p class="p-cap p-slip-cap">' +
      (rc ? 'A signed receipt' : 'A receipt') + ' records the owner’s call on each open claim, what machines settled, what nobody checked and who signed, for one exact commit.</p>';
    return '<section class="p-owner" data-progress="owner">' +
      '<div class="p-sticky p-owner-in">' +
        '<div class="p-owner-l">' +
          '<h2 class="p-h2"><span class="p-num hot" data-count="' + s.open + '">0</span> ' + words('left for') + '<br>' + words('a person.', 'hot', 120) + '</h2>' +
          '<p class="p-ctx" data-rv>Argued and Refused claims wait for a named owner — the person responsible for that part of the code.</p>' +
          '<ul class="p-open">' + rows + '</ul>' +
          '<p class="p-cap p-open-key"><span>◆ Argued</span><span>✕ Refused</span> open claims per branch</p>' +
          (aq ? '<blockquote class="p-quote" data-rv style="--c:var(--t-argued)">' +
            '<header>◆ Argued <span>#' + esc(issueOf(aq.d)) + '</span></header>' +
            '<p>' + rich(aq.c.claim) + '</p>' +
            (aq.c.why_this_tier ? '<p class="p-why"><b>Why it waits:</b> ' + rich(aq.c.why_this_tier) + '</p>' : '') +
            '<footer>Decides: ' + esc(aq.c.owner_role || 'named owner') + '</footer></blockquote>' : '') +
        '</div>' +
        '<div class="p-owner-r"><div class="p-printer" aria-hidden="true"><span class="mouth"></span></div>' + slip + cap + '</div>' +
      '</div></section>';
  }

  function secKnow(s) {
    var cmds = s.commands.slice(0, 12);
    var row = cmds.concat(cmds).map(function (c) { return '<span><b>$</b> ' + esc(c) + '</span>'; }).join('');
    var nc = s.notCheckedList.slice().sort(function (a, b) { return a.t.length - b.t.length; })[0];
    var allHunks = s.hunksSeen === s.ds.length;
    return '<section class="p-sec p-know">' +
      '<div class="p-tape" aria-hidden="true"><div class="p-tape-in">' + row + '</div></div>' +
      '<div class="p-stats">' +
        '<div class="p-stat" data-rv><div class="v"><span data-count="' + s.evidenceCount + '">0</span></div>' +
          '<div class="l">evidence files, each saved with the command that made it</div>' +
          '<div class="split"><span style="--p:' + (100 * s.script / (s.evidenceCount || 1)).toFixed(1) + '%"></span></div>' +
          '<div class="k"><span><i class="sc"></i>by script ' + s.script + '</span><span><i class="p-hd"></i>by hand ' + s.hand + '</span></div>' +
          '<p class="n">“By hand” means a person or agent ran it, not our scripts. We only say “the tool found” for script runs.</p></div>' +
        '<div class="p-stat" data-rv><div class="v"><span data-count="' + s.uncovered + '">0</span>' + (s.hunks ? '<small> of ' + fmt(s.hunks) + '</small>' : '') + '</div>' +
          '<div class="l">changed parts of the code' + (s.hunks && allHunks ? ', across all ' + s.ds.length + ' branches,' : '') + ' with no claim about them</div>' +
          '<p class="n">Nothing the agent changed goes undescribed.</p></div>' +
        '<div class="p-stat hot" data-rv><div class="v"><span data-count="' + s.notChecked + '">0</span></div>' +
          '<div class="l">things we did not check, printed on the dossiers</div>' +
          (nc ? '<p class="n">For example, #' + esc(issueOf(nc.d)) + ': “' + rich(nc.t) + '”</p>' : '') + '</div>' +
      '</div>' +
    '</section>';
  }

  function secDoors(s) {
    var tilts = [-2.2, 1.4, 2.6, -1.2];
    var cards = s.ds.map(function (d, i) {
      var open = claims(d).filter(function (c) { return !MACHINE[c.tier]; }).length;
      return '<a class="p-door" href="#/d/' + encodeURIComponent(d.__key) + '" style="--r:' + tilts[i % tilts.length] + 'deg">' +
        '<span class="no">#' + esc(issueOf(d)) + '</span>' +
        '<span class="tt">' + esc(d.title || d.branch) + '</span>' +
        (d.summary ? '<span class="p-sm">' + rich(d.summary) + '</span>' : '') +
        strip(d) +
        '<span class="ft"><span>' + (d._receipt ? 'signed by ' + esc(d._receipt.signed_by) : plural(open, 'open claim') + ', waiting') + '</span><span aria-hidden="true">→</span></span>' +
      '</a>';
    }).join('');
    var key = TIERS.map(function (t) { return '<span><i style="background:var(--t-' + lc(t) + ')"' + (MACHINE[t] ? '' : ' class="p-own"') + '></i>' + t + '</span>'; }).join('');
    return '<section class="p-sec p-doors" id="p-doors">' +
      '<h2 class="p-h2 c">' + words('Choose') + '<br>' + words('your branch.', 'hot', 140) + '</h2>' +
      '<p class="p-ctx c" data-rv>Each bar is one claim, coloured by tier. Outlined bars are open: waiting for an owner’s decision.</p>' +
      '<div class="p-key-row" data-rv>' + key + '</div>' +
      '<div class="p-door-row">' + cards + '</div>' +
    '</section>';
  }

  function rail() {
    return '<nav class="p-rail" aria-label="Chapters">' + CHAPTERS.map(function (c) {
      return '<a href="#' + c.id + '" data-to="' + c.id + '"><i></i>' + c.n + '<span> ' + esc(c.title) + '</span></a>';
    }).join('') + '</nav>';
  }

  /* ---------- behaviour ---------- */
  function progressOf(el) {
    var r = el.getBoundingClientRect(), span = r.height - innerHeight;
    return clamp(-r.top / (span || 1), 0, 1);
  }

  function setupTransitions(root) {
    root.querySelectorAll('[data-progress="trans"]').forEach(function (sec) {
      var ws = sec.querySelectorAll('.w'), line = sec.querySelector('.p-line'), dot = sec.querySelector('.p-dot'),
        chap = sec.querySelector('.p-chap'), ctx = sec.querySelector('.p-trans-ctx');
      progressFns.push(function () {
        /* t: 0 when the section top is 3/4 down the screen, 1 when it is 15% from the top —
           the sentence is fully readable before it reaches the middle */
        var t = 1;
        if (!reduce) { var top = sec.getBoundingClientRect().top; t = clamp((innerHeight * 0.75 - top) / (innerHeight * 0.6), 0, 1); }
        var l = clamp(t / 0.4, 0, 1), shown = t * 1.1 * ws.length;
        line.style.transform = 'scaleY(' + l + ')';
        dot.style.opacity = l >= 1 ? 1 : 0;
        if (chap) chap.style.opacity = 0.6 + 0.4 * l;
        for (var i = 0; i < ws.length; i++) {
          var u = clamp(shown - i, 0, 1);
          ws[i].style.opacity = (0.35 + 0.65 * u).toFixed(3);
          ws[i].style.transform = u < 1 ? 'translateY(' + ((1 - u) * 0.15).toFixed(3) + 'em)' : 'none';
        }
        if (ctx) ctx.style.opacity = (0.35 + 0.65 * clamp((t - 0.55) / 0.35, 0, 1)).toFixed(3);
      });
    });
  }

  function setupLadder(root) {
    var sec = root.querySelector('[data-progress="ladder"]');
    if (!sec) return;
    var rungs = sec.querySelectorAll('.p-rung'), cards = sec.querySelectorAll('.p-card'), meter = sec.querySelector('.p-meter i');
    var box = sec.querySelector('.p-cards');
    function fit() {
      if (reduce) { box.style.height = ''; return; }
      var h = 0;
      cards.forEach(function (c) { h = Math.max(h, c.offsetHeight); });
      box.style.height = h + 'px';
    }
    fit();
    on(window, 'resize', fit);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { if (box.isConnected) fit(); });
    if (reduce) {
      rungs.forEach(function (r) { r.classList.add('on'); });
      cards.forEach(function (c) { c.classList.add('on'); });
      return;
    }
    var last = -1;
    progressFns.push(function () {
      var p = progressOf(sec);
      var i = clamp(Math.floor(p * 5 * 0.999), 0, 4);
      meter.style.transform = 'scaleX(' + p + ')';
      if (i === last) return;
      last = i;
      rungs.forEach(function (r) { var k = +r.dataset.i; r.classList.toggle('on', k === i); r.classList.toggle('past', k < i); });
      cards.forEach(function (c) { var k = +c.dataset.i; c.classList.toggle('on', k === i); c.classList.toggle('past', k < i); });
      sec.classList.toggle('owner-side', i >= 3);
    });
  }

  function setupOwner(root) {
    var sec = root.querySelector('[data-progress="owner"]');
    if (!sec) return;
    var slip = sec.querySelector('.p-slip'), inner = sec.querySelector('.p-slip-in');
    if (!slip) return;
    progressFns.push(function () {
      var p = reduce ? 1 : clamp((progressOf(sec) - 0.05) / 0.5, 0, 1);
      slip.style.height = (p * inner.offsetHeight).toFixed(1) + 'px';
      sec.classList.toggle('signed', p >= 0.98);
    });
  }

  function setupRail(root) {
    var nav = root.querySelector('.p-rail');
    var links = nav.querySelectorAll('a');
    links.forEach(function (a) {
      on(a, 'click', function (e) {
        e.preventDefault();
        var t = document.getElementById(a.dataset.to);
        if (t) t.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' });
      });
    });
    progressFns.push(function () {
      var cur = null;
      CHAPTERS.forEach(function (c) {
        var el = document.getElementById(c.id);
        if (el && el.getBoundingClientRect().top < innerHeight * 0.5) cur = c.id;
      });
      var end = document.getElementById('p-doors');
      var show = cur && !(end && end.getBoundingClientRect().top < innerHeight * 0.6);
      nav.classList.toggle('show', !!show);
      links.forEach(function (a) { a.classList.toggle('on', a.dataset.to === cur); });
    });
  }

  function countUp(el) {
    var target = +el.dataset.count;
    if (reduce || !target) { el.textContent = fmt(target); return; }
    var t0 = performance.now(), ms = 700;
    function step(now) {
      var u = clamp((now - t0) / ms, 0, 1);
      el.textContent = fmt(target * (1 - Math.pow(1 - u, 3)));
      if (u < 1 && el.isConnected) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function setupReveals(root) {
    var els = root.querySelectorAll('[data-rv], [data-count]');
    if (reduce || !('IntersectionObserver' in window)) {
      els.forEach(function (el) { el.classList.add('in'); if (el.dataset.count != null) el.textContent = fmt(+el.dataset.count); });
      root.querySelectorAll('i[data-w]').forEach(function (i) { i.style.width = i.dataset.w + '%'; });
      return;
    }
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target;
        io.unobserve(el);
        el.classList.add('in');
        if (el.dataset.count != null) countUp(el);
        if (el.querySelectorAll) el.querySelectorAll('i[data-w]').forEach(function (i) { i.style.width = i.dataset.w + '%'; });
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -8% 0px' });
    els.forEach(function (el) { io.observe(el); });
    cleanup.push(function () { io.disconnect(); });
  }

  function tick() {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(function () { progressFns.forEach(function (f) { f(); }); });
  }

  /* ---------- public ---------- */
  function mount(app, DATA) {
    unmount();
    var landing = app.querySelector('.landing');
    if (!landing) return;
    reduce = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    var s = stats(DATA || {});
    if (!s.ds.length) return;

    var down = document.createElement('a');
    down.className = 'p-down'; down.href = '#ch-problem'; down.setAttribute('aria-label', 'Scroll to the story'); down.textContent = '↓';
    landing.appendChild(down);
    on(down, 'click', function (e) { e.preventDefault(); document.getElementById('ch-problem').scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' }); });

    /* ch.03 and ch.04 examples first, so the ladder can show different ones */
    var used = {};
    var ownerHtml = secOwner(s, used);

    var wrap = document.createElement('div');
    wrap.className = 'p-story' + (reduce ? ' p-reduce' : '');
    wrap.innerHTML =
      rail() +
      transition('An AI agent wrote the change. Now someone has to trust it.', 4, 'ch-problem',
        'You maintain an open-source library. An AI agent sends you code. You are the one who merges it.') +
      secProblem(s) +
      transition('So we turn each change into claims, and each claim says what backs it.', 4, 'ch-built',
        'A claim is one plain sentence about what the change does. An AI reviewer writes them; scripts and checks collect the evidence.') +
      secLadder(s, used) +
      transition('Whatever can be checked, a machine checks.', 3, 'ch-machine',
        'Proved, Tested and Measured claims are settled by running the real code, not by taking the agent’s word.') +
      secMachine(s) +
      transition('The rest is a judgement call, and a named person signs for it.', 5, 'ch-owner',
        'No machine may settle these. The owner reads the evidence and decides each one.') +
      ownerHtml +
      transition('Every number carries the command that made it.', 5, 'ch-know',
        'Each result is saved with the exact command behind it, so anyone can re-run it. So is what we skipped.') +
      secKnow(s) +
      secDoors(s);
    landing.insertAdjacentElement('afterend', wrap);

    cleanup.push(function () { wrap.remove(); down.remove(); });
    setupTransitions(wrap);
    setupLadder(wrap);
    setupOwner(wrap);
    setupRail(wrap);
    setupReveals(wrap);
    on(window, 'scroll', tick, { passive: true });
    on(window, 'resize', tick);
    tick();
  }

  function unmount() {
    cancelAnimationFrame(raf);
    while (cleanup.length) { try { cleanup.pop()(); } catch (e) { /* ignore */ } }
    progressFns = [];
  }

  window.EarnedTrustPitch = { mount: mount, unmount: unmount };
})();
