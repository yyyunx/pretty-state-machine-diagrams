"""Seeded workloads for evaluation and the local demo."""

from random import Random

from src.model import build_model

SIZES = (10,25,50,100,250,500)
FAMILIES = ("sparse","dense","cycles","loops","hierarchy")
HOLDOUT_SEED = 24837


def generated_case(family, size, seed=HOLDOUT_SEED):
    if family not in FAMILIES or size<8 or size>500:
        raise ValueError("Choose a known workload and 8–500 vertices.")
    rng = Random(f"{seed}:{family}:{size}")
    name = f"{family}-{size}"
    if family=="hierarchy":
        next_id = 0

        def node(kind="state", **payload):
            nonlocal next_id
            identifier = f"s{next_id}"
            next_id += 1
            return {"id":identifier,"kind":kind,**payload}

        root = node("composite",displayName="旅運處理 / Dispatch")
        parent = root
        for _ in range(min(5,size-5)):
            child = node("composite")
            parent["regions"] = [{"vertices":[child],"transitions":[]}]
            parent = child
        remaining = size-next_id
        lanes = [[] for _ in range(min(4,remaining))]
        for i in range(remaining):
            lanes[i%len(lanes)].append(node(displayName="出發確認／Contrôle ☀️ " * 3 if i%7==0 else f"站 {i}"))
        parent["regions"] = [
            {"displayName":f"服務區 {i+1}", "vertices":lane,
             "transitions":[{"sourceId":a["id"],"targetId":b["id"],"triggers":["arrival"]}
                            for a,b in zip(lane,lane[1:])]} for i,lane in enumerate(lanes)]
        cross = [{"sourceId":a[-1]["id"],"targetId":b[0]["id"],"triggers":["同步 ↔"]}
                 for a,b in zip(lanes,lanes[1:])]
        return build_model({"id":name,"regions":[{"vertices":[root],"transitions":cross}]})
    ids = list(range(size))
    vertices = [{"id":f"s{i}","kind":"state",
                 **({"displayName":f"節點 {i} / State"} if i%3==0 else {})} for i in ids]
    rng.shuffle(vertices)
    arcs = [(i,i+1) for i in ids[:-1]]
    if family == "sparse":
        arcs.extend((i,min(size-1,i+rng.randint(2,6))) for i in ids[:-3:4])
    elif family == "loops":
        arcs.extend((i,i) for i in ids)
        arcs.extend((i,i+1) for i in ids[:-1:8])
    elif family == "cycles":
        arcs.append((size-1,0))
        arcs.extend((i,(i+1+rng.randrange(1,size-1))%size) for i in ids[::4])
    else:
        arcs.extend((i,(i+1+rng.randrange(size-1))%size) for i in ids for _ in range(3))
        arcs = list(dict.fromkeys(arcs))
    transitions = [{"sourceId":f"s{a}","targetId":f"s{b}",
                    **({"triggers":[f"signal {i}"]} if i%5==0 else {})}
                   for i,(a,b) in enumerate(arcs)]
    return build_model({"id":name,"regions":[{"vertices":vertices,"transitions":transitions}]})


def holdout_cases():
    for family,size in zip(FAMILIES,(21,17,16,19,23)):
        model = generated_case(family,size)
        yield "holdout-" + model["id"],model


def stress_cases():
    for size in SIZES:
        for family in FAMILIES:
            model = generated_case(family,size)
            yield model["id"],model
