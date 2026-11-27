"""Deterministic orthogonal routing with obstacle and bend costs."""
import heapq
import unicodedata

def text_width(text):
    return sum(16 if unicodedata.east_asian_width(c) in "WF" else 9 for c in text)

def rect(b):
    return b["x"],b["y"],b["x"]+b["width"],b["y"]+b["height"]

def overlap(a,b):
    x,y,r,t=rect(a); u,v,s,w=rect(b)
    return x<s and u<r and y<w and v<t

def route(a,b,obstacles,lane=0,loop=False,used=()):
    def ports(q):
        x,y,r,t=rect(q)
        f=min(.85,.5+lane*.07)
        return [(x,y+(t-y)*f),(r,y+(t-y)*f),(x+(r-x)*f,y),(x+(r-x)*f,t)]
    starts,ends=ports(a),ports(b)
    blocks=[rect(q) for q in obstacles+[a,b]]
    xs=set(); ys=set()
    for x,y,r,t in blocks:
        xs.update((x-12-lane*4,x,r,r+12+lane*4))
        ys.update((y-12-lane*4,y,t,t+12+lane*4))
    for x,y in starts+ends:
        xs.add(x); ys.add(y)
    xs=sorted(xs); ys=sorted(ys)
    def inside(p):
        return any(x<p[0]<r and y<p[1]<t for x,y,r,t in blocks)
    def clear(p,q):
        if p[0]==q[0]:
            return not any(x<p[0]<r and min(p[1],q[1])<t and max(p[1],q[1])>y for x,y,r,t in blocks)
        return not any(y<p[1]<t and min(p[0],q[0])<r and max(p[0],q[0])>x for x,y,r,t in blocks)
    def cost(p,q):
        n=abs(p[0]-q[0])+abs(p[1]-q[1])
        for u,v in used:
            if p[0]==q[0]==u["x"]==v["x"] and max(min(p[1],q[1]),min(u["y"],v["y"]))<min(max(p[1],q[1]),max(u["y"],v["y"])):
                n+=40
            if p[1]==q[1]==u["y"]==v["y"] and max(min(p[0],q[0]),min(u["x"],v["x"]))<min(max(p[0],q[0]),max(u["x"],v["x"])):
                n+=40
        return n
    best=None
    for start in starts:
        queue=[(0,start,0)]; dist={(start,0):0}; prev={}
        while queue:
            d,p,direction=heapq.heappop(queue)
            state=(p,direction)
            if d!=dist[state]: continue
            if p in ends and p!=start:
                path=[p]
                while state in prev:
                    state=prev[state]; path.append(state[0])
                path.reverse()
                if best is None or d<best[0]: best=(d,path)
                break
            i=xs.index(p[0]); j=ys.index(p[1])
            for ni,nj,nd in ((i-1,j,1),(i+1,j,1),(i,j-1,2),(i,j+1,2)):
                if not (0<=ni<len(xs) and 0<=nj<len(ys)): continue
                q=(xs[ni],ys[nj])
                if inside(q) or not clear(p,q): continue
                if loop and (p in starts and q in ends): continue
                value=d+cost(p,q)+(18 if direction and direction!=nd else 0)
                key=(q,nd)
                if value<dist.get(key,float("inf")):
                    dist[key]=value; prev[key]=(p,direction); heapq.heappush(queue,(value,q,nd))
    if best is None:
        # Ancestor/descendant endpoint rectangles can overlap; route to boundary directly.
        p=starts[1]; q=ends[0]
        path=[p,(p[0],q[1]),q]
    else:
        path=best[1]
    out=[]
    for p in path:
        if out and p==out[-1]: continue
        if len(out)>1 and ((out[-2][0]==out[-1][0]==p[0]) or (out[-2][1]==out[-1][1]==p[1])):
            out.pop()
        out.append(p)
    return [dict(x=x,y=y) for x,y in out]

def label_position(points,text,obstacles):
    w=max(16,text_width(text)); h=20
    segments=sorted(zip(points,points[1:]),key=lambda ab:-abs(ab[0]["x"]-ab[1]["x"])-abs(ab[0]["y"]-ab[1]["y"]))
    for offset in range(8,4096,16):
        for a,b in segments:
            x=(a["x"]+b["x"])/2; y=(a["y"]+b["y"])/2
            for xx,yy in ((x-w/2,y-h-offset),(x-w/2,y+offset),(x+offset,y-h/2),(x-w-offset,y-h/2)):
                candidate=dict(x=xx,y=yy,width=w,height=h)
                if not any(overlap(candidate,q) for q in obstacles): return candidate
    return dict(x=points[0]["x"],y=max([0]+[q["y"]+q["height"] for q in obstacles])+16,width=w,height=h)
