"""Optional, measurement-only Graphviz dot adapter for flat diagrams."""

import json
import math
import subprocess

from src.geometry import anchor, box, point, rect, text_lines, text_width, transition_text
from src.layout.engine import LayoutOptions, _Placement, _label_size
from src.layout.quality import model_index


class UnsupportedDot(ValueError):
    pass


def _flatten_cubic(a,b,c,d,depth=0):
    dx,dy = d[0]-a[0],d[1]-a[1]
    length = math.hypot(dx,dy)
    flat = length and all(
        abs(dx*(p[1]-a[1])-dy*(p[0]-a[0])) <= .25*length and
        0 <= dx*(p[0]-a[0])+dy*(p[1]-a[1]) <= length*length+1e-7 for p in (b,c)
    )
    if flat or depth==7:
        yield d
        return
    def middle(p,q):
        return ((p[0]+q[0])/2,(p[1]+q[1])/2)
    ab,bc,cd = middle(a,b),middle(b,c),middle(c,d)
    l,r = middle(ab,bc),middle(bc,cd)
    center = middle(l,r)
    yield from _flatten_cubic(a,ab,l,center,depth+1)
    yield from _flatten_cubic(center,r,cd,d,depth+1)


# Fixed sizes and reserved label boxes use the same measurements as the UML engine.
def graphviz_layout(model, executable, *, timeout=8):
    vertices, _, _, edges = model_index(model)
    if len(model["regions"])!=1 or model["regions"][0].get("displayName") or any(
        v["kind"]=="composite" or v.get("pseudostateKind") not in (None,"initial","choice","junction")
        for v in vertices.values()
    ):
        raise UnsupportedDot("dot adapter is limited to a single unnamed Region with flat states, Initial, Final, Choice or Junction.")
    if not vertices:
        raise UnsupportedDot("dot adapter requires at least one vertex.")
    measuring = _Placement(model,LayoutOptions())
    node_keys = {key:f"n{i}" for i,key in enumerate(vertices)}
    edge_keys = {f"e{i}":key for i,key in enumerate(edges)}
    command = ["digraph Layout {", "graph [rankdir=LR, splines=polyline, nodesep=0.65, ranksep=0.89];",
               'node [label="",fixedsize=true];']
    for identifier,node in vertices.items():
        if node["kind"]=="state":
            w,h = measuring.size_vertex(identifier)
            shape = "box"
        else:
            w,h = measuring.symbol_size(node)
            shape = "diamond" if node.get("pseudostateKind")=="choice" else "circle"
            if node.get("displayName"):
                raise UnsupportedDot("Labeled pseudostates require an external label placement not supported by the dot adapter.")
        command.append(f"{node_keys[identifier]} [shape={shape},width={w/72:.8f},height={h/72:.8f}];")
    label_sizes = {}
    for external,key in edge_keys.items():
        edge = edges[key]
        label = transition_text(edge)
        attr = ""
        if label:
            lines = text_lines(label)
            w,h = max(20,max(text_width(line,10.5) for line in lines)+10),12*len(lines)+6
            label_sizes[key] = w,h
            attr = (f',label=<<TABLE FIXEDSIZE="TRUE" WIDTH="{math.ceil(w)}" HEIGHT="{h}" '
                    'BORDER="0" CELLBORDER="0" CELLSPACING="0"><TR><TD></TD></TR></TABLE>>')
        command.append(f'{node_keys[edge["sourceId"]]} -> {node_keys[edge["targetId"]]} [id={external}{attr}];')
    command.append("}")
    graph = subprocess.run([executable,"-Tjson"], input="\n".join(command).encode("ascii"),
                           capture_output=True,check=True,timeout=timeout)
    data = json.loads(graph.stdout)
    _,_,w,h = (float(v) for v in data["bb"].split(","))
    geometry = dict(schemaVersion=model["schemaVersion"],modelId=model["id"],
                    viewport=box(-20,-20,w+40,h+40),nodes={},regions={},edges={})
    geometry["regions"][model["regions"][0]["id"]] = {"bounds":box(0,0,w,h)}
    reversed_keys = {v:k for k,v in node_keys.items()}

    def coords(position):
        x,y = position
        return x,h-y

    for placed in data.get("objects",()):
        key = reversed_keys[placed["name"]]
        node = vertices[key]
        width,height = (measuring.size_vertex(key) if node["kind"]=="state"
                        else measuring.symbol_size(node))
        x,y = coords(tuple(map(float,placed["pos"].split(","))))
        result = {"bounds":box(x-width/2,y-height/2,width,height)}
        if node.get("displayName"):
            lw,lh = _label_size(node["displayName"])
            result["labelBounds"] = box(x-lw/2,y-height/2+5,lw,lh)
        geometry["nodes"][key] = result

    def snapped(identifier, adjacent):
        node = geometry["nodes"][identifier]["bounds"]
        x,y,r,b = rect(node)
        cx,cy = (x+r)/2,(y+b)/2
        ax,ay = adjacent
        if abs(ax-cx)/(r-x) >= abs(ay-cy)/(b-y):
            side,fraction = ("left" if ax<cx else "right"),(ay-y)/(b-y)
        else:
            side,fraction = ("top" if ay<cy else "bottom"),(ax-x)/(r-x)
        return anchor(vertices[identifier],node,side,max(.05,min(.95,fraction)))

    for placed in data.get("edges",()):
        key = edge_keys[placed["id"]]
        edge = edges[key]
        route = []
        for path in placed.get("_draw_",()):
            if path["op"] not in ("b","L"):
                continue
            points = [coords(p) for p in path["points"]]
            route.append(points[0])
            if path["op"]=="L":
                route.extend(points[1:])
            else:
                for i in range(0,len(points)-3,3):
                    route.extend(_flatten_cubic(*points[i:i+4]))
        if len(route)<2:
            raise ValueError(f"dot omitted the path for transition {key!r}.")
        route[0] = snapped(edge["sourceId"],route[1])
        route[-1] = snapped(edge["targetId"],route[-2])
        result = {"points":[point(*p) for p in route]}
        if key in label_sizes:
            lx,ly = coords(tuple(map(float,placed["lp"].split(","))))
            lw,lh = label_sizes[key]
            result["labelBounds"] = box(lx-lw/2,ly-lh/2,lw,lh)
        geometry["edges"][key] = result
    return geometry
