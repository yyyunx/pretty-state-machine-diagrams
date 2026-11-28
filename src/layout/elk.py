"""Translate only flat layouts where ELK can preserve the UML contract."""

from math import isfinite

from src.geometry import anchor, box, point, rect, text_lines, text_width, transition_text

from .engine import LayoutError, LayoutOptions, _Placement, _label_size
from .quality import evaluate, model_index
from .hybrid import passes_geometry


def elk_graph(model, options):
    vertices,_,_,edges = model_index(model)
    if (len(model["regions"])!=1 or not vertices or model["regions"][0].get("displayName")
            or any(v["kind"]=="composite" or v.get("pseudostateKind") not in
                   (None,"initial","final","junction","choice") for v in vertices.values())
            or any(v["kind"]=="pseudostate" and v.get("displayName") for v in vertices.values())):
        raise LayoutError("ELK supports a flat unnamed Region with simple states or unlabeled Initial, Final, Choice and Junction.")
    measuring = _Placement(model,LayoutOptions())
    keys = {key:f"n{i}" for i,key in enumerate(vertices)}
    children = []
    for key,vertex in vertices.items():
        w,h = measuring.size_vertex(key) if vertex["kind"]=="state" else measuring.symbol_size(vertex)
        children.append({"id":keys[key],"width":w,"height":h})
    links = []
    for i,edge in enumerate(edges.values()):
        row = {"id":f"e{i}","sources":[keys[edge["sourceId"]]],"targets":[keys[edge["targetId"]]]}
        text = transition_text(edge)
        if text:
            lines = text_lines(text)
            row["labels"] = [{"id":f"l{i}","width":max(20,max(text_width(line,10.5) for line in lines)+10),
                              "height":12*len(lines)+6,"text":" "}]
        links.append(row)
    return {"id":"root","children":children,"edges":links,"layoutOptions":{
        "elk.algorithm":"layered","elk.direction":"RIGHT" if options.direction=="horizontal" else "DOWN",
        "elk.edgeRouting":"ORTHOGONAL","elk.spacing.nodeNode":str(options.node_spacing),
        "elk.layered.spacing.nodeNodeBetweenLayers":str(options.layer_spacing),
        "elk.randomSeed":"1",
    }}


def _number(value):
    if type(value) not in (int,float) or abs(value)>1e7 or not isfinite(value):
        raise LayoutError("ELK produced invalid coordinates.")
    return value


def _attachment(vertex,bounds,endpoint,adjacent):
    x,y,r,b = rect(bounds)
    px,py = endpoint["x"],endpoint["y"]
    dx,dy = px-adjacent["x"],py-adjacent["y"]
    if abs(dx)>=abs(dy):
        side = "left" if px<(x+r)/2 else "right"
        fraction = (py-y)/(b-y)
    else:
        side = "top" if py<(y+b)/2 else "bottom"
        fraction = (px-x)/(r-x)
    return point(*anchor(vertex,bounds,side,max(0,min(1,fraction))))


def elk_geometry(model, options, external):
    graph = elk_graph(model,options)
    index = model_index(model)
    vertices,_,_,edges = index
    try:
        placed_nodes = {item["id"]:item for item in external["children"]}
        placed_edges = {item["id"]:item for item in external.get("edges",())}
        if set(placed_nodes)!={node["id"] for node in graph["children"]} or set(placed_edges)!={e["id"] for e in graph["edges"]}:
            raise LayoutError("ELK result did not preserve every node and transition.")
        w,h = _number(external["width"]),_number(external["height"])
        graph_box = box(0,0,w,h)
        layout = {"schemaVersion":model["schemaVersion"],"modelId":model["id"],
                  "viewport":box(-20,-20,w+40,h+40),"nodes":{},"edges":{},
                  "regions":{model["regions"][0]["id"]:{"bounds":graph_box}}}
        for (key,vertex),node in zip(vertices.items(),graph["children"],strict=True):
            placed = placed_nodes[node["id"]]
            x,y = _number(placed["x"]),_number(placed["y"])
            width,height = node["width"],node["height"]
            geom = layout["nodes"][key] = {"bounds":box(x,y,width,height)}
            if vertex.get("displayName"):
                lw,lh = _label_size(vertex["displayName"])
                geom["labelBounds"] = box(x+(width-lw)/2,y+5,lw,lh)
        for (key,edge),link in zip(edges.items(),graph["edges"],strict=True):
            placed = placed_edges[link["id"]]
            sections = placed["sections"]
            if len(sections)!=1:
                raise LayoutError("ELK compound edge sections are outside this adapter's supported scope.")
            section = sections[0]
            route = [point(_number(v["x"]),_number(v["y"])) for v in
                     (section["startPoint"],*section.get("bendPoints",()),section["endPoint"])]
            start,end = edge["sourceId"],edge["targetId"]
            route[0] = _attachment(vertices[start],layout["nodes"][start]["bounds"],route[0],route[1])
            route[-1] = _attachment(vertices[end],layout["nodes"][end]["bounds"],route[-1],route[-2])
            geom = layout["edges"][key] = {"points":route}
            if "labels" in link:
                label = placed["labels"][0]
                geom["labelBounds"] = box(_number(label["x"]),_number(label["y"]),
                                          link["labels"][0]["width"],link["labels"][0]["height"])
    except (TypeError,IndexError,KeyError) as error:
        raise LayoutError("ELK returned incomplete geometry.") from error
    metrics = evaluate(model,layout)
    if not passes_geometry(model,layout,metrics,index):
        raise LayoutError("ELK candidate rejected by the shared geometry checks.")
    return layout,metrics
