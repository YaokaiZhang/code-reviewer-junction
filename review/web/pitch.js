/* Earned Trust — the pitch: a scroll story below the landing hero.
   Plain JS. One idea per section. Numbers come from window.DOSSIERS where the data has them. */
(function () {
  'use strict';

  /* kinds of evidence and their base score (the formula in the confidence check) */
  var KINDS = [
    ['rebuild-compare', 'Rebuilt and compared: identical', 90],
    ['proof-model', 'Formal verification', 80],
    ['flip-test', 'Test first: fails before, passes after', 75],
    ['revert-test', 'Undo just this change: a test fails', 75],
    ['old-vs-new-run', 'Old vs new: same output', 75, '≤75'],
    ['probe', 'Experiment on the real code', 60],
    ['count', 'A number from a tool', 40],
    ['none', 'Nothing backs it', 15]
  ];
  /* what each kind of evidence means, shown on hover: plain words, why it scores that, a real example */
  var KIND_HELP = {
    'rebuild-compare': ['Run the code generator again and compare its output with the files in the change.',
      'A script compares every character of every file, so no one has to trust the AI. Hard to fake, so it scores highest.',
      'On #2297, every generated file in the change was rebuilt and matched.'],
    'old-vs-new-run': ['Run the old and the new version on the same real projects and compare the output.',
      'Same output only counts for changed lines that actually ran. So the score is 30, plus up to 45 for the share of changed lines that ran. Any difference no rule explains drops it to 15.',
      'On #2283 only 2 of 10 changed lines ran, so it scores 39. On #2297 all 22 ran: 75.'],
    'proof-model': ['Formal verification: write the rule as a small model. A prover (Dafny) checks it for every possible case, then the model is tested against the real C# code.',
      'Very strong, but the model is a copy of the code, not the code itself.',
      'On #2234 the prover found an input that still crashes the analyzer.'],
    'flip-test': ['Test first, as in TDD: each new test must fail on the old code and pass on the new code.',
      'Then the test proves the fix, and a person only has to confirm the test asks the right thing, by reading its trace.',
      'On #2283, all 3 new tests fail before and pass after.'],
    'revert-test': ['Take back only this one part of the change, then run the tests.',
      'If a test now fails, that test really depends on this part.',
      'On #2297, undoing one part makes 1 of 169 tests fail.'],
    'probe': ['Write a tiny throwaway app that hits the case, then run the real compiler or analyzer on the old and new code.',
      'It shows real behaviour, but only for the cases someone thought to try.',
      'On #2234 it showed that one warning is no longer reported.'],
    'count': ['A tool measures something, for example how much code is copy-pasted.',
      'Useful context, but a number alone cannot say the fix is right.',
      'On #2234, copy-pasted blocks in one file went from 10 to 12.'],
    'none': ['The AI says so, and nothing checks it yet.',
      'Shown so you know where to look, not as a reason to trust it.',
      ''],
    'hand': ['A person or the AI ran the check by hand, not a script.', 'Harder for anyone to repeat exactly, so it costs 10 points.', ''],
    'replay': ['The same command was run again on a fresh machine.', 'Getting the same result shows it does not depend on our setup, so it adds 5 points.', '']
  };
  var BANDS = [['high', 'High', '80+'], ['medium', 'Medium', '50–79'], ['low', 'Low', 'under 50']];
  /* learning from the project: the backtest on past pull requests */
  /* the decision shown in the trace chapter, when the data has it */
  var DEMO = 'C-2234-04';
  var LEARN = { rules: 20, prs: 37, caught: 10, breaking: 16, falseAlarm: 55 };
  var CHAPTERS = [
    { id: 'ch-problem', n: '01', title: 'The problem' },
    { id: 'ch-trace', n: '02', title: 'The trace' },
    { id: 'ch-same', n: '03', title: 'Nothing broke' },
    { id: 'ch-score', n: '04', title: 'The score' },
    { id: 'ch-owner', n: '05', title: 'Needs owner' },
    { id: 'ch-learn', n: '06', title: 'Readable' }
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
  function fmt(n) { return Math.round(n).toLocaleString('en-US'); }
  function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
  function claims(d) { return Array.isArray(d.claims) ? d.claims : []; }
  function on(t, ev, fn, opt) { t.addEventListener(ev, fn, opt); cleanup.push(function () { t.removeEventListener(ev, fn, opt); }); }
  function issueOf(d) { return d.issue != null ? d.issue : String(d.branch || '').replace(/\D+/g, ''); }
  function band(n) { return n >= 80 ? 'high' : n >= 50 ? 'medium' : 'low'; }
  function evByCheck(d, check) {
    var ev = d._evidence || {};
    var k = Object.keys(ev).filter(function (p) { return ev[p] && ev[p].check === check; })[0];
    return k ? ev[k] : null;
  }
  function decCards(d) { return ((d._decisions || {}).details || {}).cards || []; }
  /* a card fit to show in the pitch: every step checks out, a short trace, a real check behind it */
  function demoOk(c) {
    return c.verified && c.steps && c.steps.length >= 3 && c.steps.length <= 5 && (c.because || []).some(function (b) { return b.result === 'pass'; });
  }
  function conf(d) { return (d._confidence && d._confidence.details) || {}; }
  /* score and owner gate for one claim */
  function scoreOf(d, c) {
    var x = (conf(d).claims || {})[c.id] || {};
    return { score: +x.score || 0, band: x.band || band(+x.score || 0), owner: !!x.gate };
  }

  /* ---------- the numbers ---------- */
  function stats(DATA) {
    var ds = Object.keys(DATA).sort().map(function (k) { var d = DATA[k]; d.__key = k; return d; })
      .filter(function (d) { return !d.sample; });
    var s = { ds: ds, lines: 0, claims: 0, bands: { high: 0, medium: 0, low: 0 }, owner: 0,
      evidence: {}, snap: null, steps: 0, stepsOk: 0, tests: 0, replayMatch: 0, replayTotal: 0,
      kinds: {}, rules: 0, dec: 0, decSteps: 0, decOk: 0, decEv: 0, decAsk: 0, demo: null, asks: [] };
    ds.forEach(function (d) {
      var df = d.diff || {};
      s.lines += (+df.insertions || 0) + (+df.deletions || 0);
      claims(d).forEach(function (c) {
        var x = scoreOf(d, c);
        s.claims++;
        if (s.bands[x.band] != null) s.bands[x.band]++;
        if (x.owner) s.owner++;
        var g = ((conf(d).claims || {})[c.id] || {}).gate;
        if (g && g.owner && !s.ownerEx) s.ownerEx = { name: g.owner, n: (String(g.owner_basis || '').match(/\((\d+) commits\)/) || [])[1] };
      });
      var f = conf(d).formula;
      if (f && f.kinds) s.kinds = f.kinds;
      if (+conf(d).history_rules_available) s.rules = +conf(d).history_rules_available;
      var ev = d._evidence || {};
      Object.keys(ev).forEach(function (p) { if (ev[p] && !s.evidence[p]) s.evidence[p] = ev[p]; });
      /* how many changed files are generated snapshots (for the rebuild figure) */
      var dc = evByCheck(d, 'diff-classifier'), dt = dc && dc.details;
      if (dt && dt.insertions_by_category && dt.insertions_by_category.snapshot != null) {
        var nf = +dt.snapshots_total || +(dt.counts_by_category || {}).snapshot || 0;
        if (!s.snap || nf > s.snap) s.snap = nf;
      }
      ((d._tests && d._tests.details && d._tests.details.cards) || []).forEach(function (card) {
        s.tests++;
        (card.steps || []).forEach(function (st) { s.steps++; if (st.verified) s.stepsOk++; });
      });
      decCards(d).forEach(function (card) {
        s.dec++;
        if (card.ask) { s.decAsk++; s.asks.push(card.title); }
        (card.steps || []).forEach(function (st) { s.decSteps++; if (st.verified) s.decOk++; });
        (card.because || []).forEach(function (b) { if (b.evidence && b.result && b.result !== 'missing') s.decEv++; });
        if (demoOk(card) && (card.id === DEMO || !s.demo)) s.demo = { d: d, card: card };
      });
      var files = (d._replay && d._replay.details && d._replay.details.files) || {};
      Object.keys(files).forEach(function (k) {
        if (files[k] === 'match') { s.replayMatch++; s.replayTotal++; }
        else if (files[k] === 'mismatch') s.replayTotal++;
      });
    });
    return s;
  }

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
        (ctx ? '<p class="p-ctx p-trans-ctx">' + esc(ctx) + '</p>' : '') +
      '</div></section>';
  }
  function words(text, cls, delay) {
    return '<span class="p-words ' + (cls || '') + '" data-rv>' + text.split(' ').map(function (w, i) {
      return '<span class="wm"><span class="wi" style="transition-delay:' + ((delay || 0) + i * 70) + 'ms">' + esc(w) + '&nbsp;</span></span>';
    }).join('') + '</span>';
  }
  function squares(n, cls) {
    var o = ''; for (var i = 0; i < n; i++) o += '<i></i>';
    return '<span class="p-sq ' + (cls || '') + '">' + o + '</span>';
  }
  function bandKey(own) {
    return '<div class="p-bandkey">' + BANDS.map(function (b) {
      return '<span><i class="b-' + b[0] + '"></i>' + b[1] + ' <em>' + b[2] + '</em></span>';
    }).join('') + (own ? '<span><i class="p-own"></i>Needs owner</span>' : '') + '</div>';
  }

  /* ---------- sections ---------- */
  function secProblem(s) {
    var ribbon = '';
    for (var i = 0; i < 64; i++) {
      var w = 20 + ((i * 37) % 70);
      ribbon += '<i class="' + (i % 9 === 4 ? 'del' : 'add') + '" style="width:' + w + '%"></i>';
    }
    return '<section class="p-sec p-problem">' +
      '<div class="p-grid2">' +
        '<div>' +
          '<div class="p-big" data-count="' + s.lines + '">0</div>' +
          '<h2 class="p-h2">' + words('lines changed.') + '<br>' + words('Who reads them?', 'hot', 160) + '</h2>' +
        '</div>' +
        '<div class="p-choice" data-rv>' +
          '<div class="p-ribbon" aria-hidden="true">' + ribbon + '</div>' +
          '<div class="p-keys">' +
            '<span class="p-key big">Approve</span>' +
            '<span class="p-key small">Read</span>' +
          '</div>' +
          '<p class="p-cap p-keycap">Two buttons today: approve without reading, or read every line. We want a third way.</p>' +
        '</div>' +
      '</div>' +
    '</section>';
  }

  /* the kinds of evidence, as score bars */
  function secKinds(s) {
    var rows = KINDS.map(function (k) {
      var v = s.kinds[k[0]] != null ? +s.kinds[k[0]] : k[2];
      return '<li tabindex="0" data-help="' + k[0] + '"><span class="k">' + esc(k[1]) + '</span>' +
        '<span class="bar"><i class="b-' + band(v) + '" data-w="' + v + '"></i></span>' +
        '<b>' + esc(k[3] || String(v)) + '</b></li>';
    }).join('');
    return '<section class="p-sec p-kinds">' +
      '<div class="p-grid2">' +
        '<div>' +
          '<h2 class="p-h2">' + words('The evidence') + '<br>' + words('sets the score.', 'hot', 140) + '</h2>' +
          '<p class="p-ctx" data-rv>A claim gets the score of its strongest check: −10 if someone ran it by hand, +5 if a clean machine got the same result. No AI picks the number.</p>' +
          bandsBar(s) +
        '</div>' +
        '<div class="p-panel" data-rv>' +
          '<ul class="p-kbars" aria-label="Score for each kind of evidence">' + rows + '</ul>' +
          '<div class="p-adj"><span tabindex="0" data-help="hand"><b>−10</b> run by hand</span><span tabindex="0" data-help="replay"><b>+5</b> re-run on a clean machine, same result</span></div>' +
          '<div class="p-kexp" aria-live="polite"><p class="p-kexp-0">Hover or tap a row to see what it means.</p></div>' +
          bandKey() +
        '</div>' +
      '</div>' +
    '</section>';
  }

  /* how the real claims came out */
  function bandsBar(s) {
    var tot = s.claims || 1;
    var seg = BANDS.map(function (b) {
      var n = s.bands[b[0]];
      return n ? '<span class="b-' + b[0] + '" style="flex:' + n + '"><b>' + n + '</b>' + b[1] + '</span>' : '';
    }).join('');
    return '<div class="p-bands" data-rv>' +
      '<div class="p-cap"><span class="p-num hot" data-count="' + s.claims + '">0</span> claims, scored</div>' +
      '<div class="p-stack" role="img" aria-label="' + BANDS.map(function (b) { return s.bands[b[0]] + ' ' + b[1]; }).join(', ') + ' of ' + tot + '">' + seg + '</div>' +
    '</div>';
  }

  /* first script-made evidence anywhere with this check (optionally on a given branch) */
  function findEv(s, check, branch) {
    for (var k in s.evidence) {
      var e = s.evidence[k];
      if (e && e.check === check && e.produced_by !== 'hand' && (!branch || k.indexOf(branch) >= 0)) return e;
    }
    return null;
  }

  /* each check, one per row: what it does, why it counts, what it cannot tell */
  function secMachine(s) {
    var rows = [];

    var iso = s.ds.filter(function (d) { return d._isolation && d._isolation.coverage && +d._isolation.coverage.trackable; });
    var ovn = function (d) { return conf(d).old_vs_new || null; };
    var ovs = iso.map(function (d) { return ovn(d) ? +ovn(d).score : null; }).filter(function (v) { return v != null; });
    var ovLo = Math.min.apply(null, ovs), ovHi = Math.max.apply(null, ovs);
    if (iso.length && ovs.length) rows.push({ c: band(ovHi), g: 'Old vs new', v: ovLo === ovHi ? ovLo : ovLo + '–' + ovHi, h: 'Old code still works.',
      p: 'Run old and new code on the same projects. Same output, nothing broke.',
      use: 'Most changes should not change what users see.',
      why: 'No tests needed. The old code is the answer key.',
      lim: 'Lines that never ran. The score drops with them.',
      fig: '<div class="p-fig p-ran">' + iso.map(function (d) {
        var c = d._isolation.coverage, ran = +c.reached || 0, tot = +c.trackable, pc = Math.round(100 * ran / tot);
        var o = ovn(d);
        return '<div class="p-mbar' + (pc < 50 ? ' low' : '') + '"><span>#' + esc(issueOf(d)) + '</span><i data-w="' + pc + '"></i><b>' + ran + '/' + tot + '</b>' +
          (o ? '<em class="c-' + esc(o.band) + '">score ' + (+o.score) + '</em>' : '') + '</div>';
      }).join('') + '<p class="p-out">changed lines the real projects ran, and the score that gives</p></div>' });

    var nSnap = s.snap || 0;
    if (findEv(s, 'regeneration') && nSnap) rows.push({ c: 'high', g: 'Rebuilt and compared', v: 90, h: 'Rebuild the generated code.',
      p: 'Run the code generator again. Its output must match the files exactly.',
      use: 'Many edits are just docs, comments, or renamed functions.',
      why: 'Nobody edited them by hand, so nobody has to read them.',
      lim: 'If the generator itself is right.',
      fig: '<div class="p-fig p-fig-proved">' +
        '<figure>' + squares(nSnap) + '<figcaption>' + fmt(nSnap) + ' files in the change</figcaption></figure>' +
        '<b class="p-eq">=</b>' +
        '<figure>' + squares(nSnap, 'regen') + '<figcaption>' + fmt(nSnap) + ' files rebuilt</figcaption></figure></div>' });

    var pr = findEv(s, 'proof'), pd = pr && pr.details, mv = pd && pd.model_vs_csharp;
    if (pd && mv && mv.branch) {
      var vl = ((pd.dafny_verify || {}).result_line || [''])[0], nv = (String(vl).match(/(\d+) verified/) || [])[1];
      rows.push({ c: 'high', g: 'Formal verification', v: 80, h: 'Prove it for every case.',
        p: 'Model the code. A prover checks it for every possible input.',
        use: 'Some bugs hide in rare inputs no test tries.',
        why: 'Tests try a few inputs. A proof tries all of them.',
        lim: 'If the model matches the real code. So we compare them too.',
        fig: '<div class="p-fig p-proof">' +
          (nv ? '<div><b>' + nv + '</b><span>proof steps checked by the prover, 0 errors</span></div>' : '') +
          '<div class="bad"><b>1</b><span>input still crashes: a field with an empty key comes first. It goes to the reviewer as an open problem.</span></div>' +
          '<div><b>' + fmt(+mv.branch.inputs) + '</b><span>inputs, model vs real code: ' + (+mv.branch.mismatches) + ' differences</span></div>' +
          '<p class="p-out">fix #2234</p></div>' });
    }

    var ot = findEv(s, 'old-vs-new-tests', '2283') || findEv(s, 'old-vs-new-tests');
    var nT = ot && ot.details && ot.details.counts ? +ot.details.counts.evidence : 0;
    if (nT) {
      var cells = '';
      for (var i = 0; i < nT; i++) cells += '<span class="x">✗</span><span class="ok">✓</span>';
      rows.push({ c: 'medium', g: 'Test first (TDD)', v: 75, h: 'Check the test, not the code.',
        p: 'Each new test fails on the old code and passes on the new.',
        use: 'A bug fix should come with a test that shows the bug.',
        why: 'Check the test asks the right question, not every line.',
        lim: 'Cases the test does not ask about.',
        fig: '<div class="p-fig"><div class="p-tgrid">' +
          '<span class="hd">old code</span><span class="hd">new code</span>' + cells + '</div><p class="p-out">fix #2283, ' + nT + ' new tests</p></div>' });
    }

    var cc = findEv(s, 'clone-complexity'), cd = cc && cc.details;
    if (cd && cd.base && cd.branch) {
      var b0 = +cd.base.clones.duplicated_blocks, b1 = +cd.branch.clones.duplicated_blocks, mx = Math.max(b0, b1) || 1;
      rows.push({ c: 'low', g: 'A number from a tool', v: 40, h: 'Count it.',
        p: 'A tool measures something, like copy-pasted code, before and after.',
        use: 'Code can get worse without breaking.',
        why: 'It shows costs that never fail a test.',
        lim: 'If the fix is right. So it scores low.',
        fig: '<div class="p-fig">' +
          '<div class="p-mbar"><span>before</span><i data-w="' + (100 * b0 / mx).toFixed(1) + '"></i><b>' + b0 + '</b></div>' +
          '<div class="p-mbar"><span>after</span><i data-w="' + (100 * b1 / mx).toFixed(1) + '"></i><b>' + b1 + '</b></div>' +
          '<p class="p-out">copy-pasted blocks in one file, fix #2234: a cost, not a failure</p></div>' });
    }

    return '<section class="p-machine" data-progress="machine" style="--n:' + rows.length + '">' +
      '<div class="p-sticky p-machine-in">' +
        '<header class="p-mhead">' +
          '<h2 class="p-h2">' + words('Each check,') + ' ' + words('and why it counts.', 'hot', 140) + '</h2>' +
          '<ol class="p-mtabs">' + rows.map(function (r, i) {
            return '<li class="c-' + r.c + '" data-i="' + i + '"><i></i>' + esc(r.g) + '</li>';
          }).join('') + '</ol>' +
        '</header>' +
        '<div class="p-hows">' + rows.map(function (r, i) {
          return '<article class="p-how' + (i === 0 ? ' on' : '') + '">' +
            '<div class="p-how-t">' +
              '<span class="g c-' + r.c + '">score <b>' + esc(String(r.v)) + '</b></span>' +
              '<h3>' + esc(r.h) + '</h3>' +
              '<p>' + esc(r.p) + '</p>' +
              '<dl><dt>Why use it</dt><dd>' + esc(r.use) + '</dd><dt>Counts because</dt><dd>' + esc(r.why) + '</dd><dt>Can’t tell</dt><dd>' + esc(r.lim) + '</dd></dl>' +
            '</div>' +
            '<div class="p-how-f">' + r.fig + '</div>' +
          '</article>';
        }).join('') + '</div>' +
      '</div>' +
    '</section>';
  }

  /* needs owner: who does what, then a printed slip with a generic example */
  function secOwner(s) {
    var opts = ['accept', 'send back', 'reject'];
    var t = s.asks.length >= 2 ? s.asks : ['A warning users relied on is gone', 'The docs now promise something new'];
    var lines = [[t[0], 'send back'], [t[1], 'accept']];
    var chain = [
      ['AI', 'The AI writes the trace and the question. It can be wrong.'],
      ['Tools', 'Real tools test the old and the new code. A script checks every AI step against the lines it cites.'],
      ['Rule', 'The old and the new code run on the same inputs from before the change. If something users rely on comes out different, or no input runs a changed line, a fixed rule sends the claim to a person. Not the AI.'],
      ['You', 'The owner of that part answers the question. You, the reviewer, sign the change.']
    ];
    var slip = '<div class="p-slip"><div class="p-slip-in">' +
      '<h4>NEEDS OWNER</h4>' +
      '<div class="p-ex">EXAMPLE</div><hr>' +
      lines.map(function (l) {
        return '<div class="ln"><span class="p-q">' + esc(l[0]) + '</span>' +
          '<span class="p-opts">' + opts.map(function (o) {
            return '<span class="p-o' + (o === l[1] ? ' on' : '') + '"><i>' + (o === l[1] ? '✓' : '') + '</i>' + o + '</span>';
          }).join('') + '</span></div>';
      }).join('') + '<hr>' +
      '<div class="sig"><span>SIGNED</span><em>A. Maintainer</em></div>' +
    '</div></div>';
    return '<section class="p-owner" data-progress="owner">' +
      '<div class="p-sticky p-owner-in">' +
        '<div class="p-owner-l">' +
          '<h2 class="p-h2"><span class="p-num hot" data-count="' + s.owner + '">0</span> ' + words('claims') + '<br>' + words('need an owner.', 'hot', 120) + '</h2>' +
          '<ol class="p-chain" data-rv>' + chain.map(function (c) {
            return '<li><b>' + c[0] + '</b><span>' + c[1] + '</span></li>';
          }).join('') + '</ol>' +
          '<p class="p-cant" data-rv>The AI can’t set the score, remove the owner’s question, or mark its own steps as checked.</p>' +
          '<p class="p-rule" data-rv>A high score does not remove the question.</p>' +
        '</div>' +
        '<div class="p-owner-r"><div class="p-printer" aria-hidden="true"><span class="mouth"></span></div>' + slip + '</div>' +
      '</div></section>';
  }

  /* learning from the project: how its maintainers want code to read and to last */
  var RD_RULES = [
    ['Readable', 'A small helper beats #if blocks scattered through the code.'],
    ['Maintainable', 'Keep logic out of templates. Fix it fully, not with a patch.']
  ];
  function rdPhrase(f) {
    var m = f.measure || '';
    if (/preprocessor/.test(m)) return '#if logic added inside templates';
    if (/identical added block/.test(m)) return 'the same new code pasted in several places';
    if (/duplicated/.test(m)) return 'more copy-pasted lines than before';
    return 'see the change page';
  }
  function rdRow(d) {
    var fl = ((d._readability || {}).details || {}).flags || [], seen = {}, ph = [];
    fl.forEach(function (f) { var t = rdPhrase(f); if (!seen[t]) { seen[t] = 1; ph.push(t); } });
    return '<li><span class="no">#' + esc(issueOf(d)) + '</span>' +
      '<b class="' + (fl.length ? 'warn' : 'none') + '">' + fl.length + '</b>' +
      '<span class="w">' + (fl.length ? esc(ph.slice(0, 2).join('; ')) : 'nothing flagged') + '</span></li>';
  }
  function secLearn(s) {
    var L = LEARN, rules = s.rules || L.rules;
    return '<section class="p-sec p-learn">' +
      '<div class="p-grid2">' +
        '<div>' +
          '<h2 class="p-h2">' + words('Readable today.') + '<br>' + words('Maintainable later.', 'hot', 140) + '</h2>' +
          '<p class="p-ctx" data-rv><b class="p-num hot">' + rules + ' rules</b> learned from ' + L.prs + ' past pull requests: what this project’s maintainers ask for in review.</p>' +
          '<ul class="p-rdrules" data-rv>' + RD_RULES.map(function (r) {
            return '<li><span>' + r[0] + '</span>' + esc(r[1]) + '</li>';
          }).join('') + '</ul>' +
        '</div>' +
        '<div class="p-panel" data-rv>' +
          '<div class="p-lbl">Flags on these changes</div>' +
          '<ul class="p-rdflags">' + s.ds.map(rdRow).join('') + '</ul>' +
          '<p class="p-note">Tried on past pull requests first: found <b>' + L.caught + ' of ' + L.breaking + '</b> real problems. <b>' + L.falseAlarm + '%</b> of its flags were false alarms. Flags tell the reviewer where to look. They do not change the score.</p>' +
        '</div>' +
      '</div>' +
    '</section>';
  }

  /* ---------- the trace: one real decision, step by step ---------- */
  var OPWORD = { WHEN: 'when', IF: 'if', THEN: 'then', ELSE: 'else', BEFORE: 'before', NOW: 'now', ALSO: 'also', SO: 'so', BUT: 'but', GIVEN: 'given', AND: 'and' };
  function tokHtml(t) {
    return esc(t).replace(/`([^`]+)`/g, function (_, x) { return '<code>' + x + '</code>'; });
  }
  /* the lines a step points at, as row keys: "o1007" (before) or "n1008" (after) */
  function stepKeys(st) {
    var k = [], c = st.side === 'old' ? 'o' : 'n';
    for (var i = st.lines[0]; i <= st.lines[st.lines.length - 1]; i++) k.push(c + i);
    return k;
  }
  /* only the rows that matter: changed lines and lines a step points at */
  function traceRows(card) {
    var want = {};
    card.steps.forEach(function (st) { stepKeys(st).forEach(function (k) { want[k] = 1; }); });
    var out = [], gap = false;
    (card.code || []).forEach(function (g) {
      g.rows.forEach(function (r) {
        var keep = r[0] === '+' || r[0] === '-' || (r[1] && want['o' + r[1]]) || (r[2] && want['n' + r[2]]);
        if (!keep) { if (out.length) gap = true; return; }
        if (gap) out.push(null);
        gap = false;
        out.push(r);
      });
    });
    return out.slice(0, 14);
  }
  function secTrace(s) {
    if (!s.demo) return '';
    var d = s.demo.d, c = s.demo.card;
    var steps = c.steps.map(function (st, i) {
      return '<li data-i="' + i + '" data-k="' + stepKeys(st).join(' ') + '"><b>' + (OPWORD[st.op] || esc(st.op)) + '</b>' +
        '<span>' + tokHtml(st.text) + '</span><em>✓</em></li>';
    }).join('');
    var rows = traceRows(c).map(function (r) {
      if (!r) return '<div class="r gap">⋯</div>';
      var cls = r[0] === '+' ? ' add' : r[0] === '-' ? ' del' : '';
      return '<div class="r' + cls + '"' + (r[1] ? ' data-o="' + r[1] + '"' : '') + (r[2] ? ' data-n="' + r[2] + '"' : '') + '>' +
        '<i>' + (r[2] || r[1]) + '</i><s>' + (r[0] === ' ' ? '' : r[0] === '-' ? '−' : '+') + '</s><code>' + esc(r[3].trim()) + '</code></div>';
    }).join('');
    var ev = (c.because || []).filter(function (b) { return b.result; })[0];
    var file = (c.code && c.code[0] && c.code[0].file || '').split('/').pop();
    return '<section class="p-trace" data-progress="trace">' +
      '<div class="p-sticky p-trace-in">' +
        '<div class="p-trace-hd">' +
          '<h2 class="p-h2"><span class="p-num hot" data-count="' + s.dec + '">0</span> ' + words('decisions.') + ' ' + words('Each one traced.', 'hot', 120) + '</h2>' +
          '<p class="p-cap">The AI writes each step. A script checks each step against the lines it points to (✓). A real one from fix #' + esc(issueOf(d)) + ': <b>“' + esc(c.title) + '”</b></p>' +
        '</div>' +
        '<div class="p-trace-p">' +
          '<div class="p-pane p-pane-s"><div class="p-pt"><span>1</span>What the code does</div><ol>' + steps + '</ol></div>' +
          '<div class="p-pane p-pane-c"><div class="p-pt"><span>2</span>The code <small>' + esc(file) + '</small></div><div class="p-code">' + rows + '</div></div>' +
          '<div class="p-pane p-pane-w"><div class="p-pt"><span>3</span>Why</div>' +
            '<p class="p-verdict">' + esc(c.verdict) + '</p>' +
            (ev ? '<p class="p-bec">' + esc(ev.text) + '</p><span class="p-chip ' + (ev.result === 'pass' ? 'ok' : 'x') + '">' + (ev.result === 'pass' ? '✓ check passed' : '✗ check found a problem') + '</span>' : '') +
            (c.ask ? '<div class="p-ask"><b>Question for the owner</b>' + esc(c.ask) + '</div>' : '') +
          '</div>' +
        '</div>' +
      '</div></section>';
  }

  /* ---------- same code in: old vs new, and how it differs from tests ---------- */
  function secSame(s) {
    var rows = s.ds.filter(function (d) { return d._isolation && d._isolation.totals && d._isolation.totals.compared; });
    if (!rows.length) return '';
    var rowsT = [
      ['Right answer', 'The author writes it', 'The old code’s output'],
      ['Checks', 'What the author thought of', 'Everything it outputs'],
      ['Written by', 'Often the AI that made the change', 'No one'],
      ['Catches', 'Breaks someone predicted', 'Breaks nobody predicted']
    ];
    return '<section class="p-sec p-same">' +
      '<div class="p-grid2">' +
        '<div>' +
          '<h2 class="p-h2">' + words('Did it break') + '<br>' + words('anything?', 'hot', 140) + '</h2>' +
          '<p class="p-same-big" data-rv>Same input, same output.</p>' +
          '<ul class="p-rules" data-rv>' +
            '<li><b>1</b>Run old and new code on the same inputs.</li>' +
            '<li><b>2</b>Same output: nothing broke.</li>' +
            '<li><b>3</b>Different output, or a line never ran: a person decides.</li>' +
          '</ul>' +
        '</div>' +
        '<div class="p-panel" data-rv>' +
          '<table class="p-vs"><thead><tr><th></th><th>New tests</th><th class="on">Old vs new</th></tr></thead><tbody>' +
            rowsT.map(function (r) { return '<tr><th>' + esc(r[0]) + '</th><td>' + esc(r[1]) + '</td><td class="on">' + esc(r[2]) + '</td></tr>'; }).join('') +
          '</tbody></table>' +
          '<div class="p-next"><h4>The inputs</h4>' +
            '<div class="p-nrow"><b class="n">18</b><p><b>Varied types.</b> Generics, nesting, a user’s own attribute. One break found in each fix.</p></div>' +
            '<div class="p-nrow"><b class="n">4/5</b><p><b>Which inputs ran the change.</b> In #2234, 4 projects run the changed lines. The 5th never does, and its output matches.</p></div>' +
          '</div>' +
        '</div>' +
      '</div>' +
    '</section>';
  }

  function strip(d) {
    var cs = claims(d).map(function (c) { return scoreOf(d, c); }).sort(function (a, b) { return b.score - a.score; });
    return '<span class="p-strip" aria-hidden="true">' + cs.map(function (x) {
      return '<i class="b-' + x.band + (x.owner ? ' p-own' : '') + '"></i>';
    }).join('') + '</span>';
  }

  function secDoors(s) {
    var tilts = [-2.2, 1.4, 2.6, -1.2];
    var cards = s.ds.map(function (d, i) {
      var own = claims(d).filter(function (c) { return scoreOf(d, c).owner; }).length;
      return '<a class="p-door" href="#/d/' + encodeURIComponent(d.__key) + '" style="--r:' + tilts[i % tilts.length] + 'deg">' +
        '<span class="no">#' + esc(issueOf(d)) + '</span>' +
        '<span class="tt">' + esc(d.title || d.branch) + '</span>' +
        strip(d) +
        '<span class="ft"><span>' + (own ? own + (own === 1 ? ' needs' : ' need') + ' an owner' : 'nothing waiting') + '</span><span aria-hidden="true">→</span></span>' +
      '</a>';
    }).join('');
    return '<section class="p-sec p-doors" id="p-doors">' +
      '<h2 class="p-h2 c">' + words('Choose') + '<br>' + words('a change.', 'hot', 140) + '</h2>' +
      '<p class="p-ctx c" data-rv>One bar per claim, sorted by score.</p>' +
      '<div class="p-key-row" data-rv>' + bandKey(true) + '</div>' +
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
        /* t: 0 when the section top is 3/4 down the screen, 1 when it is 15% from the top */
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

  /* the checks: one sticky screen, scrolling swaps which check is shown */
  function setupMachine(root) {
    var sec = root.querySelector('[data-progress="machine"]');
    if (!sec) return;
    var arts = sec.querySelectorAll('.p-how'), tabs = sec.querySelectorAll('.p-mtabs li'), n = arts.length, cur = -1;
    function show(i) {
      if (i === cur) return;
      cur = i;
      arts.forEach(function (a, k) {
        a.classList.toggle('on', k === i);
        if (k === i) a.querySelectorAll('i[data-w]').forEach(function (b) { b.style.width = b.dataset.w + '%'; });
      });
      tabs.forEach(function (t, k) { t.classList.toggle('on', k === i); t.classList.toggle('done', k < i); });
    }
    tabs.forEach(function (t, k) {
      on(t, 'click', function () {
        var top = sec.getBoundingClientRect().top + scrollY, span = sec.offsetHeight - innerHeight;
        scrollTo({ top: top + span * (k + 0.5) / n, behavior: reduce ? 'auto' : 'smooth' });
      });
    });
    progressFns.push(function () {
      if (reduce || innerWidth <= 900) { arts.forEach(function (a) { a.classList.add('on'); a.querySelectorAll('i[data-w]').forEach(function (b) { b.style.width = b.dataset.w + '%'; }); }); cur = -2; return; }
      if (cur === -2) { cur = -1; arts.forEach(function (a) { a.classList.remove('on'); }); }
      show(Math.min(n - 1, Math.floor(progressOf(sec) * n)));
    });
  }

  function setupOwner(root) {
    var sec = root.querySelector('[data-progress="owner"]');
    if (!sec) return;
    var slip = sec.querySelector('.p-slip'), inner = sec.querySelector('.p-slip-in');
    if (!slip) return;
    progressFns.push(function () {
      /* print while the chapter scrolls in; fully printed once it fills the screen */
      var top = sec.getBoundingClientRect().top;
      var p = reduce ? 1 : clamp((0.6 * innerHeight - top) / (0.6 * innerHeight), 0, 1);
      slip.style.height = (p * inner.offsetHeight).toFixed(1) + 'px';
      sec.classList.toggle('signed', p >= 0.98);
    });
  }

  /* all steps shown; hover or focus on a step lights its code lines */
  /* the evidence chart: hover, focus or tap a row to explain it */
  function setupKinds(root) {
    var box = root.querySelector('.p-kexp');
    if (!box) return;
    var items = root.querySelectorAll('.p-kinds [data-help]'), idle;
    function html(el) {
      var h = KIND_HELP[el.getAttribute('data-help')];
      if (!h) return '';
      var name = el.querySelector('.k');
      return '<b>' + esc(name ? name.textContent : el.textContent) + '</b>' +
        '<p>' + esc(h[0]) + '</p><p class="why">' + esc(h[1]) + '</p>' + (h[2] ? '<p class="eg">' + esc(h[2]) + '</p>' : '');
    }
    function show(el) {
      var s = html(el);
      if (!s) return;
      for (var i = 0; i < items.length; i++) items[i].classList.toggle('on', items[i] === el);
      box.innerHTML = s;
    }
    /* reserve the tallest explanation's height, so the panel never jumps between rows */
    function fit() {
      var keep = box.innerHTML, mx = 0;
      box.style.minHeight = '0';
      for (var i = 0; i < items.length; i++) { var s = html(items[i]); if (s) { box.innerHTML = s; mx = Math.max(mx, box.offsetHeight); } }
      box.innerHTML = keep;
      box.style.minHeight = mx ? mx + 'px' : '';
    }
    idle = items[0] ? html(items[0]) : box.innerHTML;
    box.innerHTML = idle;
    fit();
    on(window, 'resize', fit);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
    function hide() {
      for (var i = 0; i < items.length; i++) items[i].classList.remove('on');
      box.innerHTML = idle;
    }
    Array.prototype.forEach.call(items, function (el) {
      el.addEventListener('mouseenter', function () { show(el); });
      el.addEventListener('focus', function () { show(el); });
      el.addEventListener('click', function () { show(el); });
      el.addEventListener('mouseleave', hide);
      el.addEventListener('blur', hide);
    });
  }

  function setupTrace(root) {
    var sec = root.querySelector('[data-progress="trace"]');
    if (!sec) return;
    var lis = sec.querySelectorAll('.p-pane-s li'), why = sec.querySelector('.p-pane-w'), code = sec.querySelector('.p-code');
    var n = lis.length, pick = -1;
    function show(cur) {
      lis.forEach(function (li, i) { li.classList.toggle('on', i === cur); li.classList.toggle('done', i < cur || cur >= n); });
      var keys = cur >= 0 && cur < n ? lis[cur].dataset.k.split(' ') : [];
      code.querySelectorAll('.r').forEach(function (r) {
        var hit = keys.indexOf('o' + r.dataset.o) >= 0 || keys.indexOf('n' + r.dataset.n) >= 0;
        r.classList.toggle('on', hit);
      });
      var hot = code.querySelector('.r.on');
      if (hot) code.scrollTop = Math.max(0, hot.offsetTop - code.clientHeight / 2);
      var ol = lis[0] && lis[0].parentNode, li = cur >= 0 && cur < n && pick < 0 ? lis[cur] : null;
      if (ol && li) ol.scrollTop = Math.max(0, li.offsetTop - ol.offsetTop - ol.clientHeight / 2 + li.offsetHeight / 2);
      why.classList.toggle('on', cur >= n);
    }
    lis.forEach(function (li, i) {
      li.tabIndex = 0;
      on(li, 'mouseenter', function () { pick = i; show(i); });
      on(li, 'focus', function () { pick = i; show(i); });
      on(li, 'mouseleave', function () { pick = -1; tick(); });
      on(li, 'blur', function () { pick = -1; tick(); });
    });
    progressFns.push(function () { if (pick < 0) show(n); });
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
    var t0 = performance.now(), ms = 500;
    function step(now) {
      var u = clamp((now - t0) / ms, 0, 1);
      el.textContent = fmt(target * (0.6 + 0.4 * (1 - Math.pow(1 - u, 3))));
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
    }, { threshold: 0, rootMargin: '0px' });
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

    var wrap = document.createElement('div');
    wrap.className = 'p-story' + (reduce ? ' p-reduce' : '');
    wrap.innerHTML =
      rail() +
      transition('An AI made the change. Can you see why?', 4, 'ch-problem',
        'You maintain a library: it generates code for its users and warns them about mistakes. An AI agent sends you a fix: hundreds of lines, dozens of choices.') +
      secProblem(s) +
      transition('So the AI must explain every decision.', 3, 'ch-trace',
        'In plain steps, next to the real code, with a reason.') +
      secTrace(s) +
      transition('A fix must not break what already works.', 3, 'ch-same',
        'Even when the tests are weak. So we run the old and the new library on the same real projects, and compare the output.') +
      secSame(s) +
      transition('Every reason must point to a real check.', 3, 'ch-score',
        'The AI sums up the change as claims: one short sentence each. The stronger the check behind a claim, the higher its score.') +
      secKinds(s) +
      secMachine(s) +
      transition('Some decisions belong to a person.', 3, 'ch-owner',
        'When users would notice a change, the trace ends with a question for the person who owns that part of the code.') +
      secOwner(s) +
      transition('Code is written once, then read for years.', 3, 'ch-learn',
        'We read what maintainers asked for on past pull requests, and turned it into checks.') +
      secLearn(s) +
      secDoors(s);
    landing.insertAdjacentElement('afterend', wrap);

    cleanup.push(function () { wrap.remove(); down.remove(); });
    setupTransitions(wrap);
    setupOwner(wrap);
    setupMachine(wrap);
    setupTrace(wrap);
    setupKinds(wrap);
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
