#!/usr/bin/env python3
"""Chart of the learning-loop replay: cumulative catches (of 16) and cumulative noise (of 60) by PR index,
loop (solid) vs frozen baseline (dashed). Reads review/evidence/feedback-loop.json, writes docs/feedback-loop.svg.

    python3 review/scripts/render_loop_chart.py

Standard library only. White background so it reads on GitHub light and dark themes.
"""
import json, os
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "review", "evidence", "feedback-loop.json")
OUT = os.path.join(ROOT, "docs", "feedback-loop.svg")
W, H = 900, 420
INK, MUTED, GRID = "#1f2328", "#59636e", "#d8dee4"
LOOP, BASE = "#0969da", "#bc4c00"
FONT = "font-family=\"-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif\""


def panel(x0, y0, w, h, xs, loop_y, base_y, ymax, title, ticks, learn_x, n):
    sx = lambda i: x0 + w * i / max(n - 1, 1)
    sy = lambda v: y0 + h - h * v / ymax
    out = [f'<text x="{x0}" y="{y0 - 14}" {FONT} font-size="14" font-weight="600" fill="{INK}">{escape(title)}</text>']
    for t in ticks:
        y = sy(t)
        out.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x0 + w}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{x0 - 8}" y="{y + 4:.1f}" {FONT} font-size="11" fill="{MUTED}" text-anchor="end">{t}</text>')
    for i in range(0, n, 24):
        out.append(f'<text x="{sx(i):.1f}" y="{y0 + h + 30}" {FONT} font-size="11" fill="{MUTED}" text-anchor="middle">{i}</text>')
    out.append(f'<text x="{sx(n - 1):.1f}" y="{y0 + h + 30}" {FONT} font-size="11" fill="{MUTED}" text-anchor="middle">{n - 1}</text>')
    for i in learn_x:
        out.append(f'<line x1="{sx(i):.1f}" y1="{y0 + h + 3}" x2="{sx(i):.1f}" y2="{y0 + h + 13}" stroke="{MUTED}" stroke-width="1.2"/>')
    out.append(f'<line x1="{x0}" y1="{y0 + h}" x2="{x0 + w}" y2="{y0 + h}" stroke="{MUTED}" stroke-width="1"/>')

    def path(ys):
        pts = []
        for i, v in zip(xs, ys):  # step line: a count changes at a PR
            if pts:
                pts.append(f"L{sx(i):.1f},{float(pts[-1].split(',')[1]):.1f}")
            pts.append(f"{'M' if not pts else 'L'}{sx(i):.1f},{sy(v):.1f}")
        return " ".join(pts)
    out.append(f'<path d="{path(base_y)}" fill="none" stroke="{BASE}" stroke-width="2.2" stroke-dasharray="6 4"/>')
    out.append(f'<path d="{path(loop_y)}" fill="none" stroke="{LOOP}" stroke-width="2.4"/>')
    lv, bv = loop_y[-1], base_y[-1]
    ly, by = sy(lv), sy(bv)
    if abs(ly - by) < 14:
        ly, by = (ly - 7, by + 7) if lv >= bv else (ly + 7, by - 7)
    out.append(f'<text x="{x0 + w + 6}" y="{ly + 4:.1f}" {FONT} font-size="12" font-weight="600" fill="{LOOP}">loop {lv}</text>')
    out.append(f'<text x="{x0 + w + 6}" y="{by + 4:.1f}" {FONT} font-size="12" font-weight="600" fill="{BASE}">baseline {bv}</text>')
    return out


def main():
    ev = json.load(open(SRC, encoding="utf-8"))
    d = ev["details"]
    c = d["cumulative"]
    xs, n = c["x"], len(c["x"])
    TL, TB = d["totals"]["loop"], d["totals"]["baseline"]
    learn_x = sorted({a["accepted_before_pr_index"] for a in d["accepted_overrides"]})
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
         f'aria-label="Learning loop vs frozen baseline: cumulative catches and noise by PR index">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         f'<text x="24" y="32" {FONT} font-size="17" font-weight="700" fill="{INK}">Learning loop vs frozen baseline (replay, simulated approvals)</text>',
         f'<text x="24" y="52" {FONT} font-size="12" fill="{MUTED}">{escape(f"{n} upstream PRs in date order. Catches: {TL["catches"]} vs {TB["catches"]} of {TL["positives"]} promise-concern PRs. Noise: {TL["noise"]} vs {TB["noise"]} of {TL["controls"]} merged-clean PRs flagged.")}</text>']
    pw, ph, top = 300, 215, 100
    s += panel(60, top, pw, ph, xs, c["loop_catches"], c["baseline_catches"], TL["positives"],
               f"Cumulative catches (of {TL['positives']}) - higher is better", [0, 4, 8, 12, 16], learn_x, n)
    s += panel(500, top, pw, ph, xs, c["loop_noise"], c["baseline_noise"], TL["controls"],
               f"Cumulative noise (of {TL['controls']}) - lower is better", [0, 15, 30, 45, 60], learn_x, n)
    ly = H - 18
    s += [f'<text x="210" y="{top + ph + 46}" {FONT} font-size="11" fill="{MUTED}" text-anchor="middle">PR index (stream order)</text>',
          f'<text x="650" y="{top + ph + 46}" {FONT} font-size="11" fill="{MUTED}" text-anchor="middle">PR index (stream order)</text>',
          f'<line x1="60" y1="{ly - 4}" x2="90" y2="{ly - 4}" stroke="{LOOP}" stroke-width="2.4"/>',
          f'<text x="96" y="{ly}" {FONT} font-size="12" fill="{INK}">loop: learns from each decision once it is available</text>',
          f'<line x1="420" y1="{ly - 4}" x2="450" y2="{ly - 4}" stroke="{BASE}" stroke-width="2.2" stroke-dasharray="6 4"/>',
          f'<text x="456" y="{ly}" {FONT} font-size="12" fill="{INK}">frozen baseline</text>',
          f'<line x1="590" y1="{ly - 10}" x2="590" y2="{ly}" stroke="{MUTED}" stroke-width="1.2"/>',
          f'<text x="598" y="{ly}" {FONT} font-size="12" fill="{INK}">override accepted before this PR</text>',
          '</svg>']
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(s) + "\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
