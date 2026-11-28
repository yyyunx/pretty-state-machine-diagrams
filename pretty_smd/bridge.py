"""JSON-only browser and local HTTP entry point to the Python engine."""

from dataclasses import asdict
import json

from src.layout.budget import BudgetExceeded
from src.layout.engine import LayoutOptions
from src.model import ModelError

from .pipeline import InputError, generate, load_json, prepare_model


def generated_response(result):
    return {"svg":result.svg,"model":result.model,"layout":result.layout,"quality":result.quality,
            "diagnostics":[asdict(item) for item in result.warnings]}


def options_from(request):
    values = request.get("options",{})
    if not isinstance(values,dict) or set(values)-set(vars(LayoutOptions())):
        raise InputError("Unknown or invalid layout settings.")
    return LayoutOptions(**values)


def request_action(action, request, *, timeout=10.0, max_vertices=500, max_edges=1200, progress=None):
    if not isinstance(request,dict):
        raise InputError("A JSON request object is required.")
    if action not in ("format","validate","generate"):
        raise InputError("Unknown browser operation.")
    source = request.get("source")
    if not isinstance(source,str):
        raise InputError("The request needs a JSON source string.")
    input_format = request.get("format","auto")
    if input_format=="pa":
        raise InputError("Raw Process Algebra requires a confirmed R/S Converter.")
    parsed = load_json(source)
    if action=="format":
        return {"formatted":json.dumps(parsed,ensure_ascii=False,indent=2,allow_nan=False),
                "diagnostics":[]}
    limits = dict(max_vertices=max_vertices,max_edges=max_edges)
    if action=="validate":
        model,warnings = prepare_model(parsed,input_format=input_format,**limits)
        return {"model":model,"diagnostics":[asdict(item) for item in warnings]}
    options = options_from(request)
    algorithm,mode = request.get("algorithm","topology"),request.get("mode","balanced")
    compare,rotate = request.get("compare",False),request.get("allowRotate",False)
    if (algorithm not in ("topology","legacy","advanced") or mode not in ("fast","balanced","quality")
            or type(compare) is not bool or type(rotate) is not bool):
        raise InputError("Unknown layout algorithm, mode or comparison setting.")
    if algorithm=="legacy":
        limits = dict(max_vertices=min(max_vertices,48),max_edges=min(max_edges,96))
    result = generate(parsed,input_format=input_format,options=options,algorithm=algorithm,mode=mode,
                      timeout=timeout,allow_rotate=rotate,progress=progress,**limits)
    response = generated_response(result)
    if compare and algorithm!="topology":
        if progress is not None:
            progress("compare")
        try:
            baseline = generate(result.model,input_format="smd",options=options,algorithm="topology",
                                timeout=min(5,timeout),**limits)
            response["baseline"] = generated_response(baseline)
        except ValueError as error:
            response["diagnostics"].append({"severity":"warning","code":"baseline-failed",
                                            "path":"","message":str(error)})
    return response


def error_response(error):
    if isinstance(error,ModelError):
        return 422,{"diagnostics":[asdict(item) for item in error.diagnostics]}
    if isinstance(error,BudgetExceeded):
        timed_out = "time limit" in str(error)
        status,code = (504,"layout-timeout") if timed_out else (422,"layout-work-limit")
    else:
        status,code = 422,"input-error"
    return status,{"diagnostics":[{"severity":"error","code":code,"path":"","message":str(error)}]}


def execute_json(action, payload, progress=None):
    """Validate a bounded JSON message. User input is always data."""
    try:
        body = request_action(action,load_json(payload),progress=progress)
        status = 200
    except (ValueError,UnicodeError,RecursionError) as error:
        status,body = error_response(error)
    return json.dumps({"status":status,"body":body},ensure_ascii=False,allow_nan=False)
