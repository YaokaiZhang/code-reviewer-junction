/* Earned Trust — the pitch: a scroll story below the landing hero.
   Plain JS. Every number comes from window.DOSSIERS at runtime. */
(function () {
  'use strict';

  var TIERS = ['Proved', 'Tested', 'Measured', 'Argued', 'Refused'];
  var MACHINE = { Proved: 1, Tested: 1, Measured: 1 };
  var GLYPH = { Proved: '■', Tested: '▲', Measured: '●', Argued: '◆', Refused: '✕' };
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
  function rich(s) { return esc(s).replace(/`([^`]+)`/g, '<code>$1</code>'); }
  function lc(s) { return String(s || '').toLowerCase(); }
  function fmt(n) { return Math.round(n).toLocaleString('en-US'); }
  function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
  function claims(d) { return Array.isArray(d.claims) ? d.claims : []; }
  function on(t, ev, fn, opt) { t.addEventListener(ev, fn, opt); cleanup.push(function () { t.removeEventListener(ev, fn, opt); }); }
  function shortCmd(c) {
    return String(c || '').replace(/^cd \S+ && /, '').replace(/\/(?:tmp|home|root)\/\S*?\/(review\/)/g, '$1');
  }
  function issueOf(d) { return d.issue != null ? d.issue : String(d.branch || '').replace(/\D+/g, ''); }

  /* claim-coverage evidence, wherever the renderer put it */
  function coverageOf(d) {
    if (d._coverage && d._coverage.details) return d._coverage;
    var ev = d._evidence || {}, k = Object.keys(ev).filter(function (p) { return ev[p] && ev[p].check === 'claim-coverage'; })[0];
    return k ? ev[k] : null;
  }

  /* ---------- the numbers ---------- */
  function stats(DATA) {
    var ds = Object.keys(DATA).sort().map(function (k) { var d = DATA[k]; d.__key = k; return d; })
      .filter(function (d) { return !d.sample; });
    var s = {
      ds: ds, lines: 0, files: 0, claims: 0, tiers: {}, byTier: {}, evidence: {}, script: 0, hand: 0,
      hunks: 0, uncovered: 0, notChecked: 0, commands: [], open: 0
    };
    TIERS.forEach(function (t) { s.tiers[t] = 0; s.byTier[t] = []; });
    ds.forEach(function (d) {
      var df = d.diff || {};
      s.lines += (+df.insertions || 0) + (+df.deletions || 0);
      s.files += +df.files || 0;
      s.notChecked += (d.not_checked || []).length;
      s.uncovered += (d.uncovered_diff_parts || []).length;
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
      if (cv) s.hunks += +cv.details.hunks_total || 0;
    });
    s.evidenceCount = s.script + s.hand;
    return s;
  }

  function evOf(item) {
    var ev = (item.d._evidence || {});
    return (item.c.evidence || []).map(function (p) { return ev[p]; }).filter(Boolean);
  }
  function pickTested(s) {
    var best = null;
    s.byTier.Tested.forEach(function (it) {
      evOf(it).forEach(function (e) {
        if (!best && lc(e.result) === 'pass' && /fail on base and pass on branch/.test(e.summary || '') && e.produced_by !== 'hand') best = { it: it, e: e };
      });
    });
    if (!best && s.byTier.Tested[0]) best = { it: s.byTier.Tested[0], e: evOf(s.byTier.Tested[0])[0] };
    return best;
  }
  function pickProved(s) {
    var it = s.byTier.Proved.slice().sort(function (a, b) { return a.c.claim.length - b.c.claim.length; })[0];
    return it ? { it: it, e: evOf(it)[0] } : null;
  }
  function pickCoverage(s) {
    var best = null;
    s.ds.forEach(function (d) {
      var e = coverageOf(d);
      if (e && (!best || e.details.hunks_total > best.e.details.hunks_total)) best = { d: d, e: e };
    });
    return best;
  }
  function pickRefused(s) {
    return s.byTier.Refused.filter(function (it) { return it.c.owner_role; })
      .sort(function (a, b) { return a.c.claim.length - b.c.claim.length; })[0] || s.byTier.Refused[0];
  }
  function exampleFor(s, t) {
    var xs = s.byTier[t].slice().sort(function (a, b) { return a.c.claim.length - b.c.claim.length; });
    return xs[0];
  }

  /* ---------- pieces ---------- */
  function transition(text, hot, ch) {
    var words = text.split(' ');
    var c = ch && CHAPTERS.filter(function (x) { return x.id === ch; })[0];
    return '<section class="p-trans"' + (c ? ' id="' + c.id + '" data-chapter="' + c.id + '"' : '') + ' data-progress="trans">' +
      '<div class="p-sticky p-trans-in">' +
        (c ? '<div class="p-chap"><span>' + c.n + '</span><i></i>' + esc(c.title) + '</div>' : '') +
        '<div class="p-line"></div><div class="p-dot"></div>' +
        '<p class="p-sentence">' + words.map(function (w, i) {
          return '<span class="w' + (i >= words.length - hot ? ' hot' : '') + '">' + esc(w) + ' </span>';
        }).join('') + '</p>' +
      '</div></section>';
  }
  function words(text, cls, delay) {
    return '<span class="p-words ' + (cls || '') + '" data-rv>' + text.split(' ').map(function (w, i) {
      return '<span class="wm"><span class="wi" style="transition-delay:' + ((delay || 0) + i * 70) + 'ms">' + esc(w) + '&nbsp;</span></span>';
    }).join('') + '</span>';
  }
  function strip(d) {
    var cs = claims(d).slice().sort(function (a, b) { return TIERS.indexOf(a.tier) - TIERS.indexOf(b.tier); });
    return '<span class="p-strip">' + cs.map(function (c) {
      return '<i style="background:var(--t-' + lc(c.tier) + ')"' + (MACHINE[c.tier] ? '' : ' class="own"') + '></i>';
    }).join('') + '</span>';
  }
  function term(cmd, e) {
    var res = e ? lc(e.result) : '';
    return '<div class="p-term">' +
      (cmd ? '<div class="p-cmd"><span>$</span> ' + esc(cmd) + '</div>' : '') +
      (e ? '<div class="p-out"><b class="' + esc(res) + '">' + esc(String(e.result || '').toUpperCase()) + '</b> ' + esc(e.summary || '') + '</div>' : '') +
      '</div>';
  }

  /* ---------- sections ---------- */
  function secProblem(s) {
    var rows = s.ds.map(function (d) {
      var df = d.diff || {}, n = (+df.insertions || 0) + (+df.deletions || 0);
      return '<li><span class="b">#' + esc(issueOf(d)) + '</span>' +
        '<span class="bar"><i data-w="' + (100 * n / s.lines).toFixed(2) + '"></i></span>' +
        '<span class="n">' + fmt(n) + '</span></li>';
    }).join('');
    // a ribbon of fake diff gutter marks — pure texture, no text
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
          '<ul class="p-bars" data-rv>' + rows + '</ul>' +
        '</div>' +
        '<div class="p-choice" data-rv>' +
          '<div class="p-ribbon" aria-hidden="true">' + ribbon + '</div>' +
          '<div class="p-keys">' +
            '<span class="p-key big">Approve</span>' +
            '<span class="p-key small">Read</span>' +
          '</div>' +
        '</div>' +
      '</div>' +
    '</section>';
  }

  function secLadder(s) {
    var rows = TIERS.map(function (t, i) {
      return (i === 3 ? '<li class="split" aria-hidden="true"><span>machine</span><span>owner</span></li>' : '') +
        '<li class="p-rung c-' + lc(t) + '" data-i="' + i + '" style="--c:var(--t-' + lc(t) + ')">' +
          '<b>' + GLYPH[t] + '</b><span class="t">' + t + '</span><span class="n">' + s.tiers[t] + '</span></li>';
    }).join('');
    var cards = TIERS.map(function (t, i) {
      var ex = exampleFor(s, t);
      if (!ex) return '';
      return '<article class="p-card" data-i="' + i + '" style="--c:var(--t-' + lc(t) + ')">' +
        '<header><span class="g">' + GLYPH[t] + ' ' + t + '</span><span class="id">' + esc(ex.c.id) + '</span></header>' +
        '<p>' + rich(ex.c.claim) + '</p>' +
        (ex.c.owner_role ? '<footer>✎ ' + esc(ex.c.owner_role) + '</footer>' : '<footer class="m">settled by machine</footer>') +
      '</article>';
    }).join('');
    return '<section class="p-ladder" data-progress="ladder">' +
      '<div class="p-sticky p-ladder-in">' +
        '<div class="p-ladder-head"><span class="p-big sm" data-count="' + s.claims + '">0</span><span class="p-h3">claims</span></div>' +
        '<div class="p-ladder-body">' +
          '<ol class="p-rungs">' + rows + '</ol>' +
          '<div class="p-cards">' + cards + '</div>' +
        '</div>' +
        '<div class="p-meter"><i></i></div>' +
      '</div></section>';
  }

  function secMachine(s) {
    var pr = pickProved(s), te = pickTested(s), co = pickCoverage(s);
    var cols = [];
    if (pr) cols.push(
      '<article class="p-ev" style="--c:var(--t-proved)" data-rv>' +
        '<header><b>■</b> Proved <span>#' + esc(issueOf(pr.it.d)) + '</span></header>' +
        '<p>' + rich(pr.it.c.claim) + '</p>' + term(pr.e && shortCmd(pr.e.command), pr.e) +
      '</article>');
    if (te) cols.push(
      '<article class="p-ev" style="--c:var(--t-tested)" data-rv>' +
        '<header><b>▲</b> Tested <span>#' + esc(issueOf(te.it.d)) + '</span></header>' +
        '<p>' + rich(te.it.c.claim) + '</p>' + term(te.e && shortCmd(te.e.command), te.e) +
      '</article>');
    if (!co) {
      var ms = null;
      s.byTier.Measured.forEach(function (it) { evOf(it).forEach(function (e) { if (!ms && e.produced_by !== 'hand' && e.command) ms = { it: it, e: e }; }); });
      if (ms) cols.push(
        '<article class="p-ev" style="--c:var(--t-measured)" data-rv>' +
          '<header><b>●</b> Measured <span>#' + esc(issueOf(ms.it.d)) + '</span></header>' +
          '<p>' + rich(ms.it.c.claim) + '</p>' + term(shortCmd(ms.e.command), ms.e) +
        '</article>');
    } else {
      var dt = co.e.details, cov = dt.hunks_total - dt.hunks_uncovered;
      cols.push(
        '<article class="p-ev" style="--c:var(--t-measured)" data-rv>' +
          '<header><b>●</b> Measured <span>#' + esc(issueOf(co.d)) + '</span></header>' +
          '<div class="p-ratio"><span data-count="' + cov + '">0</span><i>/</i>' + fmt(dt.hunks_total) + '</div>' +
          '<div class="p-hunks" data-rv><i style="--p:' + (100 * cov / (dt.hunks_total || 1)).toFixed(1) + '%"></i></div>' +
          '<p class="sub">changed hunks with a claim</p>' +
          term(shortCmd(co.e.command), co.e) +
        '</article>');
    }
    var m = s.tiers.Proved + s.tiers.Tested + s.tiers.Measured;
    return '<section class="p-sec p-machine">' +
      '<h2 class="p-h2"><span class="p-num" data-count="' + m + '">0</span> ' + words('settled') + '<br>' + words('by machine.', 'hot', 120) + '</h2>' +
      '<div class="p-evs">' + cols.join('') + '</div>' +
    '</section>';
  }

  function secOwner(s) {
    var rows = s.ds.map(function (d) {
      var a = 0, r = 0;
      claims(d).forEach(function (c) { if (c.tier === 'Argued') a++; if (c.tier === 'Refused') r++; });
      function g(n, t) { var o = ''; for (var i = 0; i < n; i++) o += '<b style="--c:var(--t-' + lc(t) + ');transition-delay:' + (i * 90) + 'ms">' + GLYPH[t] + '</b>'; return o; }
      return '<li data-rv><span class="b">#' + esc(issueOf(d)) + '</span><span class="g">' + g(a, 'Argued') + g(r, 'Refused') + '</span></li>';
    }).join('');
    var rf = pickRefused(s);
    var d0 = rf && rf.d, picks = d0 ? claims(d0).filter(function (c) { return !MACHINE[c.tier]; }) : [];
    var auto = d0 ? claims(d0).filter(function (c) { return MACHINE[c.tier]; }) : [];
    var rc = d0 && d0._receipt;
    var signer = rc ? rc.signed_by : (rf && rf.c.owner_role) || '';
    var slip = d0 ? '<div class="p-slip" aria-hidden="true"><div class="p-slip-in">' +
      '<h4>RECEIPT</h4><div class="c">' + esc(d0.branch) + ' @ ' + esc(d0.head || '') + '</div><hr>' +
      picks.map(function (c, i) {
        var pk = rc ? ((rc.picks || []).filter(function (p) { return p.id === c.id; })[0] || {}).pick : ['send back', 'reject', 'accept'][i % 3];
        return '<div class="ln"><span>' + GLYPH[c.tier] + ' ' + esc(c.id) + '</span><span class="pk">' + esc(String(pk || '').toUpperCase()) + '</span></div>';
      }).join('') + '<hr>' +
      '<div class="auto">AUTO ' + auto.map(function (c) { return GLYPH[c.tier] + ' ' + esc(c.id); }).join(' · ') + '</div><hr>' +
      '<div class="sig"><span>SIGNED</span><em>' + esc(signer) + '</em></div>' +
    '</div><span class="tear"></span></div>' : '';
    return '<section class="p-owner" data-progress="owner">' +
      '<div class="p-sticky p-owner-in">' +
        '<div class="p-owner-l">' +
          '<h2 class="p-h2"><span class="p-num hot" data-count="' + s.open + '">0</span> ' + words('left for') + '<br>' + words('a person.', 'hot', 120) + '</h2>' +
          '<ul class="p-open">' + rows + '</ul>' +
          (rf ? '<blockquote class="p-quote" data-rv style="--c:var(--t-refused)">' +
            '<header>✕ Refused <span>' + esc(rf.c.id) + '</span></header>' +
            '<p>' + rich(rf.c.claim) + '</p>' +
            '<footer>✎ ' + esc(rf.c.owner_role || '') + '</footer></blockquote>' : '') +
        '</div>' +
        '<div class="p-owner-r"><div class="p-printer"><span class="mouth"></span></div>' + slip + '</div>' +
      '</div></section>';
  }

  function secKnow(s) {
    var cmds = s.commands.slice(0, 12);
    var row = cmds.concat(cmds).map(function (c) { return '<span><b>$</b> ' + esc(c) + '</span>'; }).join('');
    return '<section class="p-sec p-know">' +
      '<div class="p-tape" aria-hidden="true"><div class="p-tape-in">' + row + '</div></div>' +
      '<div class="p-stats">' +
        '<div class="p-stat" data-rv><div class="v"><span data-count="' + s.evidenceCount + '">0</span></div>' +
          '<div class="l">evidence files, each with its command</div>' +
          '<div class="split"><span style="--p:' + (100 * s.script / (s.evidenceCount || 1)).toFixed(1) + '%"></span></div>' +
          '<div class="k"><span><i class="sc"></i>script ' + s.script + '</span><span><i class="hd"></i>by hand ' + s.hand + '</span></div></div>' +
        '<div class="p-stat" data-rv><div class="v"><span data-count="' + s.uncovered + '">0</span>' + (s.hunks ? '<small> / ' + fmt(s.hunks) + '</small>' : '') + '</div>' +
          '<div class="l">changed hunks with no claim</div></div>' +
        '<div class="p-stat hot" data-rv><div class="v"><span data-count="' + s.notChecked + '">0</span></div>' +
          '<div class="l">things we did not check, printed on the dossier</div></div>' +
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
        strip(d) +
        '<span class="ft"><span>' + (d._receipt ? 'signed' : open + ' open') + '</span><span>→</span></span>' +
      '</a>';
    }).join('');
    return '<section class="p-sec p-doors" id="p-doors">' +
      '<h2 class="p-h2 c">' + words('Choose') + '<br>' + words('your branch.', 'hot', 140) + '</h2>' +
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
      var ws = sec.querySelectorAll('.w'), line = sec.querySelector('.p-line'), dot = sec.querySelector('.p-dot'), chap = sec.querySelector('.p-chap');
      progressFns.push(function () {
        var p = reduce ? 1 : progressOf(sec);
        var l = clamp(p / 0.25, 0, 1), shown = Math.max(0, (p - 0.18) / 0.55) * ws.length;
        line.style.transform = 'scaleY(' + l + ')';
        dot.style.opacity = l >= 1 ? 1 : 0;
        if (chap) chap.style.opacity = 0.35 + 0.65 * l;
        for (var i = 0; i < ws.length; i++) {
          var t = clamp(shown - i, 0, 1);
          ws[i].style.opacity = 0.12 + 0.88 * t;
          ws[i].style.transform = 'translateY(' + ((1 - t) * 0.25).toFixed(3) + 'em)';
          ws[i].style.filter = t < 1 ? 'blur(' + ((1 - t) * 4).toFixed(2) + 'px)' : 'none';
        }
      });
    });
  }

  function setupLadder(root) {
    var sec = root.querySelector('[data-progress="ladder"]');
    if (!sec) return;
    var rungs = sec.querySelectorAll('.p-rung'), cards = sec.querySelectorAll('.p-card'), meter = sec.querySelector('.p-meter i');
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
      var p = reduce ? 1 : clamp((progressOf(sec) - 0.1) / 0.6, 0, 1);
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
    var t0 = performance.now(), ms = 1500;
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
      root.querySelectorAll('.p-bars i').forEach(function (i) { i.style.width = i.dataset.w + '%'; });
      return;
    }
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target;
        io.unobserve(el);
        el.classList.add('in');
        if (el.dataset.count != null) countUp(el);
        el.querySelectorAll && el.querySelectorAll('.p-bars i, i[data-w]').forEach(function (i) { i.style.width = i.dataset.w + '%'; });
        if (el.matches('.p-bars')) el.querySelectorAll('i[data-w]').forEach(function (i) { i.style.width = i.dataset.w + '%'; });
      });
    }, { threshold: 0.3 });
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
      transition('An AI agent wrote the change. Now someone has to trust it.', 4, 'ch-problem') +
      secProblem(s) +
      transition('So the change becomes claims, and each claim says what backs it.', 4, 'ch-built') +
      secLadder(s) +
      transition('Whatever can be checked, a machine checks.', 3, 'ch-machine') +
      secMachine(s) +
      transition('The rest is a judgement call, and a named person signs for it.', 5, 'ch-owner') +
      secOwner(s) +
      transition('Every number carries the command that made it.', 5, 'ch-know') +
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
