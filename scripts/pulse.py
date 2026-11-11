"""Draw the activity line (pulse-{light,dark}.svg) from real contributions, styled as a monitoring panel.

Run daily by .github/workflows/pulse.yml. Stdlib only:

    GITHUB_TOKEN=... python3 scripts/pulse.py <login> <out_dir>
    python3 scripts/pulse.py --demo <out_dir>          # made-up data, for previews
"""
import datetime as dt
import json
import os
import random
import sys
import urllib.request
from pathlib import Path

from palette import MONO, THEMES

W, H = 1000, 124
L, R = 8, 984               # plot x range
TOP, BOTTOM = 40, 94        # plot y range
MONTH_Y = 114
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
QUERY = """query($login: String!) { user(login: $login) { contributionsCollection { contributionCalendar {
  totalContributions weeks { firstDay contributionDays { contributionCount } } } } } }"""


def fetch(login):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}", "User-Agent": "profile-pulse"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors"):
        sys.exit(f"GraphQL error: {body['errors']}")
    cal = body["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = [(dt.date.fromisoformat(w["firstDay"]), sum(d["contributionCount"] for d in w["contributionDays"]))
             for w in cal["weeks"]]
    return cal["totalContributions"], weeks


def demo():
    rng = random.Random(4)
    start = dt.date.today() - dt.timedelta(weeks=52)
    weeks = [(start + dt.timedelta(weeks=i), max(0, int(rng.gauss(12, 8) + 9 * (i % 11 > 7)))) for i in range(53)]
    return sum(c for _, c in weeks), weeks


def smooth(pts):
    """Catmull-Rom through pts as cubic Beziers, never dipping below the baseline."""
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(BOTTOM, p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(BOTTOM, p2[1] - (p3[1] - p1[1]) / 6))
        d += f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d


def month_labels(weeks, xs):
    out, last = [], -1e9
    for (day, _), x in zip(weeks, xs):
        if day.day <= 7 and x - last > 40 and x < R - 20:   # first week that starts in a new month
            out.append(f'<text class="small" x="{x:.1f}" y="{MONTH_Y}">{MONTHS[day.month - 1]}</text>')
            last = x
    return "".join(out)


def build(total, weeks, t):
    counts = [c for _, c in weeks]
    peak = max(counts)
    n = len(counts)
    xs = [L + i * (R - L) / (n - 1) for i in range(n)]
    pts = [(x, BOTTOM - c / (peak or 1) * (BOTTOM - TOP)) for x, c in zip(xs, counts)]
    line = smooth(pts)
    ex, ey = pts[-1]
    this_week = counts[-1]
    dot = t["a2"] if this_week else t["muted"]
    grid = "".join(f'<line class="grid" x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}"/>' for y in (TOP, (TOP + BOTTOM) / 2))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{total} contributions in the last 12 months, {this_week} this week">
<defs>
  <linearGradient id="g" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="0">
    <stop offset="0" stop-color="{t['a1']}"/><stop offset=".55" stop-color="{t['am']}"/><stop offset="1" stop-color="{t['a2']}"/>
  </linearGradient>
  <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{t['am']}" stop-opacity=".18"/><stop offset="1" stop-color="{t['am']}" stop-opacity="0"/>
  </linearGradient>
</defs>
<style>
  text {{ font-family: {MONO}; }}
  .head {{ font-size: 13px; fill: {t['muted']}; }}
  .num {{ fill: {t['fg']}; }}
  .small {{ font-size: 10.5px; fill: {t['muted']}; }}
  .dot {{ fill: {dot}; }}
  .grid {{ stroke: {t['muted']}; stroke-opacity: .18; stroke-dasharray: 2 4; }}
  .base {{ stroke: {t['muted']}; stroke-opacity: .3; }}
  .line {{ fill: none; stroke: url(#g); stroke-width: 2; stroke-linejoin: round;
          stroke-dasharray: 100; stroke-dashoffset: 100; animation: draw 2.4s cubic-bezier(.4,0,.2,1) .2s forwards; }}
  .area {{ fill: url(#area); opacity: 0; animation: show 1.2s ease 1.6s forwards; }}
  .end {{ opacity: 0; animation: show .3s ease 2.5s forwards; }}
  .ping {{ fill: none; stroke: {dot}; stroke-width: 1.5; opacity: 0; transform-box: fill-box; transform-origin: center;
          animation: ping 2s ease-out 2.6s infinite; }}
  @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
  @keyframes show {{ to {{ opacity: 1; }} }}
  @keyframes ping {{ 0% {{ opacity: .9; transform: scale(.6); }} 70%, 100% {{ opacity: 0; transform: scale(2.6); }} }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ animation: none !important; }}
    .line {{ stroke-dashoffset: 0; }} .area, .end {{ opacity: 1; }} .ping {{ display: none; }}
  }}
</style>
<text class="head" x="{L}" y="18"><tspan class="num">{total:,}</tspan> contributions · last 12 months</text>
<text class="head" x="{R}" y="18" text-anchor="end"><tspan class="dot">●</tspan> <tspan class="num">{this_week}</tspan> this week</text>
<text class="small" x="{R}" y="{TOP - 5}" text-anchor="end">peak {peak}/wk</text>
{grid}
<line class="base" x1="{L}" y1="{BOTTOM}" x2="{R}" y2="{BOTTOM}"/>
{month_labels(weeks, xs)}
<path class="area" d="{line}L{ex:.1f} {BOTTOM}L{L} {BOTTOM}Z"/>
<path class="line" d="{line}" pathLength="100"/>
<g class="end"><circle class="ping" cx="{ex:.1f}" cy="{ey:.1f}" r="5"/><circle class="dot" cx="{ex:.1f}" cy="{ey:.1f}" r="3.5"/></g>
</svg>
'''


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    total, weeks = demo() if sys.argv[1] == "--demo" else fetch(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        (out / f"pulse-{name}.svg").write_text(build(total, weeks, theme), encoding="utf-8")
    print(f"{total} contributions, {len(weeks)} weeks -> {out}")


if __name__ == "__main__":
    main()
