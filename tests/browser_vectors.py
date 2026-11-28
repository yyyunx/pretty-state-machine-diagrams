"""Native acceptance vectors for the browser runtime regression."""

import json
import sys
from time import perf_counter

from pretty_smd.benchmark import cases
from pretty_smd.bridge import error_response, request_action
from pretty_smd.stress import HOLDOUT_SEED, generated_case, holdout_cases


def reference_vectors():
    for name,model in (*cases(),*holdout_cases()):
        yield name,"topology","balanced",model
        if name in ("linear","resolvedBranch","nested","orthogonal","pseudostates"):
            for algorithm,mode in (("legacy","balanced"),("advanced","fast"),("advanced","balanced"),
                                   ("advanced","quality")):
                yield name,algorithm,mode,model


def native(payload):
    start = perf_counter()
    try:
        result = request_action("generate",payload)
        status = 200
    except ValueError as error:
        status,result = error_response(error)
    return {"status":status,"body":result,"elapsedMs":(perf_counter()-start)*1000}


def build(stress=False):
    vectors = []
    source = reference_vectors() if not stress else (
        (f"sparse-{n}",algorithm,mode,generated_case("sparse",n,HOLDOUT_SEED))
        for n in (10,25,50,100,250,500) for algorithm,mode in (
            ("topology","balanced"),("advanced","fast"),("advanced","balanced"),("advanced","quality")))
    for name,algorithm,mode,model in source:
        payload = {"source":json.dumps(model,ensure_ascii=False),"format":"smd",
                   "algorithm":algorithm,"mode":mode}
        vectors.append({"case":name,"payload":payload,"expected":native(payload)})
    return vectors


if __name__=="__main__":
    sys.stdout.buffer.write(json.dumps(build("--stress" in sys.argv),ensure_ascii=False,
                                       allow_nan=False).encode("utf-8"))
