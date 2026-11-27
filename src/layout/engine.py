"""Initial deterministic recursive layout; geometry only, no model mutation."""
from collections import defaultdict

def box(x,y,w,h):
    return dict(x=x,y=y,width=w,height=h)

def point(x,y):
    return dict(x=x,y=y)

def layout(model):
    nodes, regions, edges = {}, {}, {}
    transitions = []
    def measure(v):
        if v["kind"] == "composite":
            sizes = [region_size(r) for r in v["regions"]]
            return max([160, len(v.get("displayName",""))*9+32]+[w for w,h in sizes])+32, sum(h for w,h in sizes)+48
        if v["kind"] in ("pseudostate","final"):
            return 24,24
        lines = [v.get("displayName","")]
        for k, val in v.get("behaviors",{}).items():
            lines.extend(k+": "+s for s in (val if isinstance(val,list) else [val]))
        return max(100,max(map(len,lines))*9+24), max(48,len(lines)*20+16)
    def region_size(r):
        sizes=[measure(v) for v in r["vertices"]]
        return max(120,sum(w for w,h in sizes)+64*max(0,len(sizes)-1)+48), max([48]+[h for w,h in sizes])+80
    def place_region(r,x,y,w,h,separator=False):
        p={"bounds":box(x,y,w,h)}
        name=r.get("displayName")
        if name:
            lw=min(w-16,max(16,len(name)*9))
            p["labelBounds"]=box(x+(w-lw)/2,y-10 if separator else y+4,lw,20)
        if separator:
            if name:
                a=p["labelBounds"]["x"]-6
                b=a+lw+12
                p["separatorSegments"]=[[point(x,y),point(a,y)],[point(b,y),point(x+w,y)]]
            else:
                p["separatorSegments"]=[[point(x,y),point(x+w,y)]]
        regions[r["id"]]=p
        cx=x+24
        for v in r["vertices"]:
            vw,vh=measure(v)
            vy=y+40
            n={"bounds":box(cx,vy,vw,vh)}
            if v.get("displayName"):
                n["labelBounds"]=box(cx+4,vy+4,vw-8,20)
            nodes[v["id"]]=n
            if v["kind"]=="composite":
                ry=vy+32
                for i,child in enumerate(v["regions"]):
                    _,rh=region_size(child)
                    place_region(child,cx+16,ry,vw-32,rh,i>0)
                    ry+=rh
            cx+=vw+64
        transitions.extend(r["transitions"])
    sizes=[region_size(r) for r in model["regions"]]
    width=max(w for w,h in sizes)
    y=32
    for i,(r,(_,h)) in enumerate(zip(model["regions"],sizes)):
        place_region(r,32,y,width,h,i>0)
        y+=h
    lanes=defaultdict(int)
    for t in transitions:
        a=nodes[t["sourceId"]]["bounds"]
        b=nodes[t["targetId"]]["bounds"]
        key=tuple(sorted((t["sourceId"],t["targetId"])))
        lane=lanes[key]; lanes[key]+=1
        ax=a["x"]+a["width"]/2; bx=b["x"]+b["width"]/2
        ay=a["y"]+a["height"]; by=b["y"]+b["height"]
        ly=max(ay,by)+16+lane*12
        if t["sourceId"]==t["targetId"]:
            bx=a["x"]+a["width"]; by=a["y"]+a["height"]/2
            pts=[point(ax,ay),point(ax,ly),point(bx+16+lane*12,ly),point(bx+16+lane*12,by),point(bx,by)]
        else:
            pts=[point(ax,ay),point(ax,ly),point(bx,ly),point(bx,by)]
        e={"points":pts}
        label=t.get("sourceText") or " ".join(t.get("triggers",[])+[t.get("guard",""),t.get("effect","")]).strip()
        if label:
            lw=max(16,len(label)*9)
            e["labelBounds"]=box((ax+bx)/2-lw/2,ly-20,lw,18)
        edges[t["id"]]=e
    all_boxes=[p[k] for group in (nodes,regions,edges) for p in group.values() for k in ("bounds","labelBounds") if k in p]
    all_points=[p for e in edges.values() for p in e["points"]]
    left=min([0]+[b["x"]-16 for b in all_boxes])
    right=max([width+64]+[b["x"]+b["width"]+16 for b in all_boxes]+[p["x"]+16 for p in all_points])
    bottom=max([y+32]+[b["y"]+b["height"]+16 for b in all_boxes]+[p["y"]+16 for p in all_points])
    return dict(schemaVersion=model["schemaVersion"],modelId=model["id"],viewport=box(left,0,right-left,bottom),nodes=nodes,regions=regions,edges=edges)
