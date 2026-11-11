"""The system behind the header: services, stores and the wires between them.

A node's depth `d` is the hop at which a request reaches it (gateway = 0).
Every edge points from a lower depth to a higher one.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Node:
    key: str            # also the label under the node
    x: float
    y: float
    d: int
    kind: str           # gw | svc | db | queue | llm


NODES = [
    Node("gateway", 622, 112, 0, "gw"),
    Node("auth", 714, 58, 1, "svc"),
    Node("api", 714, 150, 1, "svc"),
    Node("redis", 812, 34, 2, "db"),
    Node("rag", 812, 104, 2, "svc"),
    Node("queue", 812, 172, 2, "queue"),
    Node("llm", 918, 66, 3, "llm"),
    Node("pgvector", 918, 128, 3, "db"),
    Node("postgres", 918, 186, 3, "db"),
]
NODE = {n.key: n for n in NODES}

EDGES = [
    ("gateway", "auth"), ("gateway", "api"),
    ("api", "redis"), ("api", "rag"), ("api", "queue"),
    ("rag", "llm"), ("rag", "pgvector"), ("queue", "postgres"),
]

RADIUS = dict(gw=9, svc=6, db=8, queue=6, llm=11)

for _a, _b in EDGES:
    assert NODE[_a].d < NODE[_b].d, f"edge {_a}>{_b} must go deeper"


def curve(a, b):
    """Cubic Bezier from node a to node b, leaving and arriving horizontally."""
    xm = (a.x + b.x) / 2
    return f"M{a.x:.1f} {a.y:.1f}C{xm:.1f} {a.y:.1f} {xm:.1f} {b.y:.1f} {b.x:.1f} {b.y:.1f}"


def shape(n, cls):
    """SVG for one node's body. Stores are cylinders, the queue is three messages, the LLM a hexagon."""
    x, y, r = n.x, n.y, RADIUS[n.kind]
    if n.kind == "gw":
        return f'<rect class="{cls}" x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r}" height="{2 * r}" rx="5"/>'
    if n.kind == "svc":
        return f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="{r}"/>'
    if n.kind == "db":
        rx, ry, h = 7, 2.6, 10
        top = y - h / 2
        return (f'<path class="{cls}" d="M{x - rx:.1f} {top:.1f}v{h}a{rx} {ry} 0 0 0 {2 * rx} 0v-{h}z"/>'
                f'<ellipse class="{cls} cap" cx="{x:.1f}" cy="{top:.1f}" rx="{rx}" ry="{ry}"/>')
    if n.kind == "queue":
        return "".join(f'<rect class="{cls}" x="{x + dx - 2.6:.1f}" y="{y - 2.6:.1f}" width="5.2" height="5.2" rx="1.4"/>'
                       for dx in (-7, 0, 7))
    if n.kind == "llm":
        pts = " ".join(f"{x + r * c:.1f},{y + r * s:.1f}"
                       for c, s in ((0, -1), (.866, -.5), (.866, .5), (0, 1), (-.866, .5), (-.866, -.5)))
        return f'<polygon class="{cls} hex" points="{pts}"/>'
    raise ValueError(n.kind)
