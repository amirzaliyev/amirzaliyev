"""Generate the animated profile header: assets/hero-{light,dark}.svg

One loop per phrase, shaped like a request through a real backend:
  the prompt sends a request -> the gateway fans it out along that phrase's route
  -> the deepest services (stores, the LLM) work -> the response flows back
  -> it streams into the prompt token by token, like an LLM answer.
Behind it, a strip of request traces (a span waterfall) swept by a time cursor.

Pure SVG + SMIL + CSS, no JS, so GitHub renders it inside an <img>. Stdlib only:

    python3 scripts/hero.py              # writes assets/
    python3 scripts/hero.py <out_dir>    # preview somewhere else
"""
import random
import re
import sys
from pathlib import Path

from palette import MONO, THEMES
from topology import EDGES, NODE, NODES, RADIUS, curve, shape

NAME = "amirzaliyev"
ROLE = "Full-stack engineer · backend & AI"
# Each phrase is the answer to a request that takes this route through the topology.
PHRASES = [
    ("designing APIs", ["gateway>auth", "gateway>api", "api>redis"]),
    ("scaling Postgres", ["gateway>api", "api>redis", "api>queue", "queue>postgres"]),
    ("wiring LLMs into products", ["gateway>auth", "gateway>api", "api>redis", "api>rag", "rag>llm"]),
    ("building RAG pipelines", ["gateway>api", "api>rag", "rag>pgvector", "rag>llm"]),
    ("shipping agents to prod", ["gateway>auth", "gateway>api", "api>rag", "rag>pgvector", "rag>llm",
                                 "api>queue", "queue>postgres"]),
]

W, H = 1000, 300
TX, NAME_Y, ROLE_Y, PROMPT_Y = 8, 98, 138, 178
ADV = 12.04                 # monospace advance at 20px; every typed glyph is placed explicitly
BASE = TX + 2 * ADV         # first column after "$ "
DOLLAR_X = TX + ADV / 2     # centre of the "$": requests leave from it and answers land on it
RAIL_Y = 198                # the wire from the prompt to the gateway runs under the prompt line

CYCLE = 5.0                 # one phrase (s)
BEAM = 0.45                 # prompt <-> gateway (s)
HOP, BHOP = 0.36, 0.28      # one depth step for the request / the response (s)
THINK, THINK_LLM = 0.25, 0.6    # how long the deepest services work before answering (s)
CLEAR = 0.12                # the prompt clears this long before the next answer lands (s)
TOKEN_DT = (0.07, 0.14)     # gap between streamed tokens (s)
GLOW, FADE = 0.7, 0.4       # flash decay on arrival, fade after the node has replied (s)
WORKING = dict(llm=.85)     # brightness while a node waits on its reply; default below
WORKING_DEFAULT = .35
RING = 0.8                  # ripple (s)
SCAN = 9.0                  # time cursor sweep over the traces (s)
EPS = 0.01

# Background traces: (root span, duration label, width px, children as (start, width, depth[, "tok"]))
# with start/width as a share of the root. "tok" spans are drawn as streamed tokens.
TRACES = [
    ("POST /v1/ask", "412ms", 232, [(0, .06, 1), (.07, .05, 1), (.13, .30, 1), (.13, .11, 2), (.25, .18, 2),
                                    (.45, .53, 1), (.51, .47, 2, "tok")]),
    ("GET /v1/orders", "38ms", 150, [(0, .12, 1), (.14, .08, 1), (.24, .56, 1), (.82, .16, 1)]),
    ("POST /v1/agents/run", "1.83s", 286, [(0, .04, 1), (.05, .22, 1), (.29, .16, 1), (.30, .12, 2), (.47, .15, 1),
                                           (.49, .11, 2), (.64, .34, 1), (.70, .28, 2, "tok")]),
    ("POST /v1/ingest", "96ms", 190, [(0, .08, 1), (.11, .62, 1), (.13, .56, 2), (.76, .22, 1)]),
]
WF_X, WF_GAP, WF_LABEL_Y, WF_Y, WF_ROW = 14, 36, 224, 230, 7

SANS = '-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Helvetica, Arial, sans-serif'


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------- timing

def plan():
    """Absolute times (s) of every event across one loop of all phrases."""
    rng = random.Random(5)
    cycles = []
    for k, (phrase, route) in enumerate(PHRASES):
        edges = [tuple(e.split(">")) for e in route]
        for e in edges:
            assert e in EDGES, f"{phrase!r} uses unknown edge {e}"
        keys = {"gateway"} | {x for e in edges for x in e}
        rmax = max(NODE[x].d for x in keys)
        sent = k * CYCLE
        start = sent + BEAM
        answer = start + rmax * HOP + (THINK_LLM if "llm" in keys else THINK)
        back = answer + rmax * BHOP

        def reply(key):  # when this node sends its response upstream
            return answer + (rmax - NODE[key].d) * BHOP

        chunks = re.findall(r" ?\w{1,5}| ?[^\w ]+", phrase)
        assert "".join(chunks) == phrase, phrase
        land = back + BEAM
        tokens, t, i = [], land + 0.04, 0
        for c in chunks:
            tokens.append((i, c, t))
            i += len(c)
            t += rng.uniform(*TOKEN_DT)
        cycles.append(dict(
            phrase=phrase, sent=sent, back=back, land=land, tokens=tokens,
            fwd=[(a, b, start + NODE[a].d * HOP, (NODE[b].d - NODE[a].d) * HOP) for a, b in edges],
            bwd=[(a, b, reply(b), (NODE[b].d - NODE[a].d) * BHOP) for a, b in edges],
            nodes={x: (start + NODE[x].d * HOP, reply(x)) for x in keys},
        ))
    return cycles


def anim(attr, frames, total, rest, discrete=False):
    """SMIL animation over one loop. frames: [(seconds, value)]; `rest` holds at both ends."""
    pts = [(0.0, rest)] + sorted(frames, key=lambda f: f[0]) + [(total, rest)]
    assert all(0 <= t1 <= t2 <= total for (t1, _), (t2, _) in zip(pts, pts[1:])), (attr, pts)
    kt = ";".join(f"{t / total:.5f}" for t, _ in pts)
    vs = ";".join(v if isinstance(v, str) else f"{v:g}" for _, v in pts)
    mode = ' calcMode="discrete"' if discrete else ""
    return (f'<animate attributeName="{attr}" dur="{total:g}s" repeatCount="indefinite"{mode} '
            f'keyTimes="{kt}" values="{vs}"/>')


def flow(events, total, dash):
    """Run one dash along a pathLength=100 path per (start, duration) event."""
    frames = []
    for t, dur in events:
        frames += [(t, dash), (t + dur, -100), (t + dur + EPS, dash)]
    return anim("stroke-dashoffset", frames, total, dash)


def ring(x, y, r, times, total):
    rs, ops = [], []
    for t in times:
        rs += [(t, r), (t + RING, r * 2.2), (t + RING + EPS, r)]
        ops += [(t, 0), (t + EPS, .9), (t + RING, 0)]
    return (f'<circle class="ring" cx="{x:.1f}" cy="{y:.1f}" r="{r:g}" opacity="0">'
            f'{anim("r", rs, total, r)}{anim("opacity", ops, total, 0)}</circle>')


# ---------------------------------------------------------------- layers

def typing(cycles, total):
    """Streamed tokens per phrase plus the cursor that follows them."""
    texts, cursor = [], []
    for k, c in enumerate(cycles):
        off = cycles[(k + 1) % len(cycles)]["land"] - CLEAR    # cleared just before the next answer lands
        cursor.append((off, f"{BASE:.1f}"))
        for i, chunk, on in c["tokens"]:
            glyphs = chunk.lstrip(" ")
            i += len(chunk) - len(glyphs)
            xs = " ".join(f"{BASE + (i + j) * ADV:.1f}" for j in range(len(glyphs)))
            rest, frames = (0, [(on, 1), (off, 0)]) if on < off else (1, [(off, 0), (on, 1)])
            texts.append(f'<text class="mono tok" x="{xs}" y="{PROMPT_Y}" opacity="{rest}">{esc(glyphs)}'
                         f'{anim("opacity", frames, total, rest, discrete=True)}</text>')
            cursor.append((on, f"{BASE + (i + len(glyphs)) * ADV:.1f}"))
    # at t=0 the loop's last phrase is still on screen
    rest = f"{BASE + len(cycles[-1]['phrase']) * ADV:.1f}"
    cur = (f'<rect class="cursor" x="{rest}" y="{PROMPT_Y - 16}" width="10" height="20" rx="1">'
           f'{anim("x", cursor, total, rest, discrete=True)}</rect>')
    return "".join(texts) + cur


def still(phrase):
    """What reduced-motion viewers see instead of the stream."""
    xs = " ".join(f"{BASE + j * ADV:.1f}" for j in range(len(phrase)))
    return (f'<g class="still"><text class="mono tok" x="{xs}" y="{PROMPT_Y}">{esc(phrase)}</text>'
            f'<rect class="cursor" x="{BASE + len(phrase) * ADV + 4:.1f}" y="{PROMPT_Y - 16}" width="10" height="20" rx="1"/></g>')


def network(cycles, total):
    edges, fwd, bwd = [], [], []
    for a, b in EDGES:
        d = curve(NODE[a], NODE[b])
        edges.append(f'<path class="edge" d="{d}"/>')
        fe = [(t, dur) for c in cycles for x, y, t, dur in c["fwd"] if (x, y) == (a, b)]
        be = [(t, dur) for c in cycles for x, y, t, dur in c["bwd"] if (x, y) == (a, b)]
        if fe:
            fwd.append(f'<path class="fwd" d="{d}" pathLength="100" stroke-dashoffset="14">{flow(fe, total, 14)}</path>')
        if be:
            bwd.append(f'<path class="bwd" d="{curve(NODE[b], NODE[a])}" pathLength="100" stroke-dashoffset="8">'
                       f'{flow(be, total, 8)}</path>')

    cores, hots, rings, labels = [], [], [], []
    for n in NODES:
        r = RADIUS[n.kind]
        cores.append(shape(n, "core"))
        labels.append(f'<text class="lbl" x="{n.x:.1f}" y="{n.y + r + 13:.1f}" text-anchor="middle">{n.key}</text>')
        events = [c["nodes"][n.key] for c in cycles if n.key in c["nodes"]]
        if not events:
            continue
        lvl = WORKING.get(n.key, WORKING_DEFAULT)
        frames = []
        for arrive, replied in events:
            hold = max(arrive + GLOW, replied)
            frames += [(arrive, 0), (arrive + EPS, 1), (arrive + GLOW, lvl), (hold, lvl), (hold + FADE, 0)]
        hots.append(f'<g opacity="0">{shape(n, "hot")}{anim("opacity", frames, total, 0)}</g>')
        times = [arrive for arrive, _ in events]
        if n.key == "gateway":                       # it also ripples when the response comes back
            times += [c["back"] for c in cycles]
        rings.append(ring(n.x, n.y, r + 2, times, total))
    return edges, fwd, bwd, cores, hots, rings, labels


def rail():
    """Wire from under the "$" to the gateway, and the same wire reversed."""
    gw = NODE["gateway"]
    bx, by, ex, ey = DOLLAR_X, PROMPT_Y + 8, gw.x - RADIUS["gw"] - 1, gw.y
    out = (f"M{bx:.1f} {by}C{bx:.1f} {RAIL_Y} {bx + 10:.1f} {RAIL_Y} {bx + 26:.1f} {RAIL_Y}"
           f"L548 {RAIL_Y}C586 {RAIL_Y} 590 {ey} {ex} {ey}")
    back = (f"M{ex} {ey}C590 {ey} 586 {RAIL_Y} 548 {RAIL_Y}"
            f"L{bx + 26:.1f} {RAIL_Y}C{bx + 10:.1f} {RAIL_Y} {bx:.1f} {RAIL_Y} {bx:.1f} {by}")
    return out, back


def traces():
    """Span waterfall. Fill only, so the same group can be drawn muted and lit."""
    out, x = [], WF_X
    font = f"font-family='{MONO}' font-size='10'"
    for label, dur, w, spans in TRACES:
        out.append(f'<text x="{x}" y="{WF_LABEL_Y}" {font}>{esc(label)}</text>')
        out.append(f'<text x="{x + w}" y="{WF_LABEL_Y}" text-anchor="end" opacity=".7" {font}>{dur}</text>')
        out.append(f'<rect x="{x}" y="{WF_Y}" width="{w}" height="3.5" rx="1.75" opacity=".7"/>')
        for row, (s, share, depth, *style) in enumerate(spans, 1):
            sx, y, sw = x + s * w, WF_Y + row * WF_ROW, max(share * w, 3)
            op = .5 if depth == 1 else .3
            if style:  # streamed tokens: a run of small ticks
                out += [f'<rect x="{tx:.1f}" y="{y}" width="1.8" height="3.5" opacity="{op}"/>'
                        for tx in [sx + j * 4 for j in range(int(sw // 4))]]
            else:
                out.append(f'<rect x="{sx:.1f}" y="{y}" width="{sw:.1f}" height="3.5" rx="1.75" opacity="{op}"/>')
        x += w + WF_GAP
    return "".join(out)


# ---------------------------------------------------------------- build

def build(t):
    cycles = plan()
    total = CYCLE * len(cycles)
    assert cycles[-1]["tokens"][-1][2] < total, "last phrase must finish streaming inside the loop"

    edges, fwd, bwd, cores, hots, rings, labels = network(cycles, total)
    out, back = rail()
    beams = (f'<path class="beam" d="{out}" pathLength="100" stroke-dashoffset="22">'
             f'{flow([(c["sent"], BEAM) for c in cycles], total, 22)}</path>'
             f'<path class="beam" d="{back}" pathLength="100" stroke-dashoffset="22">'
             f'{flow([(c["back"], BEAM) for c in cycles], total, 22)}</path>')
    title = f"{NAME} — {ROLE}"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{esc(title)}">
<title>{esc(title)}</title>
<defs>
  <linearGradient id="g" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="0">
    <stop offset="0" stop-color="{t['a1']}"/><stop offset=".55" stop-color="{t['am']}"/><stop offset="1" stop-color="{t['a2']}"/>
  </linearGradient>
  <linearGradient id="sl" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{t['am']}" stop-opacity="0"/><stop offset=".4" stop-color="{t['am']}"/>
    <stop offset="1" stop-color="{t['am']}" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="edgefade" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".06" stop-color="#fff"/>
    <stop offset=".94" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="band" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".85" stop-color="#fff" stop-opacity=".6"/>
    <stop offset="1" stop-color="#fff"/>
  </linearGradient>
  <radialGradient id="spot"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
  <pattern id="dots" width="18" height="18" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".9" fill="{t['muted']}"/></pattern>
  <mask id="fade"><rect width="{W}" height="{H}" fill="url(#edgefade)"/></mask>
  <mask id="gridmask"><ellipse cx="785" cy="110" rx="250" ry="135" fill="url(#spot)"/></mask>
  <mask id="scan" maskUnits="userSpaceOnUse" x="-200" y="0" width="{W + 400}" height="{H}">
    <rect class="sweep" x="-160" y="0" width="160" height="{H}" fill="url(#band)"/>
  </mask>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="2.2" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <g id="wf">{traces()}</g>
</defs>
<style>
  .name {{ font: 600 56px {SANS}; letter-spacing: -1.5px; fill: {t['fg']};
          opacity: 0; animation: rise .9s cubic-bezier(.2,.7,.2,1) .1s forwards; }}
  .mono {{ font: 400 20px {MONO}; }}
  .role {{ fill: {t['muted']}; opacity: 0; animation: rise .9s cubic-bezier(.2,.7,.2,1) .3s forwards; }}
  .prompt {{ opacity: 0; animation: rise .9s cubic-bezier(.2,.7,.2,1) .5s forwards; }}
  .ps, .tok, .cursor {{ fill: url(#g); }}
  .cursor {{ animation: blink 1.1s steps(1) infinite; }}
  .lbl {{ font: 400 11px {MONO}; fill: {t['muted']}; }}
  .edge {{ fill: none; stroke: {t['muted']}; stroke-opacity: .26; stroke-width: 1.2; }}
  .fwd, .bwd, .beam {{ fill: none; stroke: url(#g); stroke-linecap: round; }}
  .fwd {{ stroke-width: 2.2; stroke-dasharray: 14 200; }}
  .bwd {{ stroke-width: 1.4; stroke-opacity: .75; stroke-dasharray: 8 200; }}
  .beam {{ stroke-width: 2.2; stroke-dasharray: 22 200; }}
  .core {{ fill: {t['node']}; }}
  .core.cap {{ stroke: {t['muted']}; stroke-opacity: .55; stroke-width: 1; }}
  .core.hex {{ stroke: url(#g); stroke-width: 1.5; }}
  .hot {{ fill: url(#g); }}
  .ring {{ fill: none; stroke: url(#g); stroke-width: 1.4; }}
  .wf-base {{ fill: {t['muted']}; opacity: 0; animation: wfin 1.6s ease .8s forwards; }}
  .wf-lit {{ fill: url(#g); }}
  .sweep, .scanline {{ transform: translateX(-200px); animation: scan {SCAN:g}s cubic-bezier(.45,0,.55,1) 1.2s infinite; }}
  .scanline {{ stroke: url(#sl); stroke-width: 1.2; }}
  .still {{ display: none; }}
  @keyframes rise  {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes blink {{ 0%, 50% {{ opacity: 1; }} 50.01%, 100% {{ opacity: 0; }} }}
  @keyframes wfin  {{ to {{ opacity: .5; }} }}
  @keyframes scan  {{ 0% {{ transform: translateX(-200px); }} 70%, 100% {{ transform: translateX({W + 200}px); }} }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ animation: none !important; }}
    .name, .role, .prompt {{ opacity: 1; }}
    .wf-base {{ opacity: .5; }}
    .anim, .scanline, .wf-lit {{ display: none; }}
    .still {{ display: inline; }}
  }}
</style>
<rect x="545" y="0" width="455" height="215" fill="url(#dots)" mask="url(#gridmask)" opacity=".4"/>
<g mask="url(#fade)">
  <use class="wf-base" href="#wf" xlink:href="#wf"/>
  <g mask="url(#scan)"><use class="wf-lit" href="#wf" xlink:href="#wf" filter="url(#glow)"/></g>
  <line class="scanline" x1="0" y1="{WF_LABEL_Y - 14}" x2="0" y2="{H}"/>
</g>
<text class="name" x="{TX - 2}" y="{NAME_Y}">{esc(NAME)}</text>
<text class="mono role" x="{TX}" y="{ROLE_Y}">{esc(ROLE)}</text>
<g class="prompt">
  <text class="mono ps" x="{TX}" y="{PROMPT_Y}">$</text>
  {still(cycles[0]["phrase"])}
  <g class="anim">{typing(cycles, total)}</g>
</g>
<path class="edge" d="{out}"/>
<g>{"".join(edges)}</g>
<g class="anim">{"".join(bwd)}</g>
<g class="anim" filter="url(#glow)">{"".join(fwd)}{beams}</g>
<g>{"".join(cores)}</g>
<g class="anim" filter="url(#glow)">{"".join(hots)}</g>
<g class="anim">{"".join(rings)}</g>
<g>{"".join(labels)}</g>
</svg>
'''


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        p = out / f"hero-{name}.svg"
        p.write_text(build(theme), encoding="utf-8")
        print(f"{p.name} {p.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
