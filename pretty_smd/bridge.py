"""JSON-only browser and local HTTP entry point to the Python engine."""

from dataclasses import asdict
import json
from time import perf_counter

from src.layout.budget import BudgetExceeded
from src.layout.editor import collapse_projection, edit_layout, validate_locks, validate_scene
from src.layout.engine import LayoutOptions
from src.layout.quality import evaluate
from src.model import ModelError
from src.renderer import render

from .pipeline import InputError, generate, load_json, prepare_model


def generated_response(result):
    return {"svg":result.svg,"model":result.model,"layout":result.layout,"quality":result.quality,
            "diagnostics":[asdict(item) for item in result.warnings]}


def options_from(request):
    values = request.get("options",{})
    if not isinstance(values,dict) or set(values)-set(vars(LayoutOptions())):
        raise InputError("Unknown or invalid layout settings.")
    return LayoutOptions(**values)


def _scene(model, layout, quality, warnings=()):
    return {"model":model,"layout":layout,"quality":quality,"svg":render(model,layout),
            "diagnostics":[asdict(item) for item in warnings]}


def _projection(model, layout, collapsed, options, timeout):
    view, geometry, summary = collapse_projection(model,layout,collapsed,options=options,timeout=timeout)
    return dict(_scene(view,geometry,evaluate(view,geometry)),summary=summary)


def _edit_action(action, request, parsed, limits, timeout):
    if action=="workspace":
        fields = {"version","model","layout","options","algorithm","mode","flags","locked","collapsed"}
        if not isinstance(parsed,dict) or set(parsed)!=fields or type(parsed["version"]) is not int or parsed["version"]!=1:
            raise InputError("Invalid workspace version or fields.")
        if parsed["algorithm"] not in ("topology","legacy","advanced","hybrid","elk") or parsed["mode"] not in ("fast","balanced","quality"):
            raise InputError("Unknown saved algorithm or search mode.")
        flags = parsed["flags"]
        if (not isinstance(flags,dict) or set(flags)!={"allowRotate","compare","useElk"}
                or any(type(value) is not bool for value in flags.values())):
            raise InputError("Invalid workspace engine flags.")
        options = options_from(parsed)
        model,warnings = prepare_model(parsed["model"],input_format="smd",**limits)
        layout = parsed["layout"]
        quality = validate_scene(model,layout,timeout=timeout)
        validate_locks(layout,parsed["locked"])
        collapsed = parsed["collapsed"]
        projection = None if collapsed==[] else _projection(model,layout,collapsed,options,timeout)
        return dict(_scene(model,layout,quality,warnings),workspace=parsed,
                    projection=projection)
    model,warnings = prepare_model(parsed,input_format="smd",**limits)
    layout = request.get("layout")
    options = options_from(request)
    validate_scene(model,layout,timeout=timeout)
    if action=="collapse":
        return _projection(model,layout,request.get("collapsed"),options,timeout)
    edited = edit_layout(model,layout,request.get("moves"),locked=request.get("locked"),options=options,timeout=timeout)
    return dict(_scene(model,edited.layout,edited.quality,warnings),edit=edited.edit)


def request_action(action, request, *, timeout=10.0, max_vertices=500, max_edges=1200, progress=None, adapter=None):
    if not isinstance(request,dict):
        raise InputError("A JSON request object is required.")
    if action not in ("format","validate","generate","elk-input","edit","collapse","workspace"):
        raise InputError("Unknown browser operation.")
    source = request.get("source")
    if not isinstance(source,str):
        raise InputError("The request needs a JSON source string.")
    input_format = request.get("format","auto")
    converter = adapter if input_format=="pa" else None
    if input_format=="pa" and converter is None:
        raise InputError("Raw Process Algebra requires a confirmed R/S Converter.")
    if converter is not None and action not in ("validate","generate","elk-input"):
        raise InputError("Use a resolved SMD JSON document for this operation.")
    parsed = source if converter is not None else load_json(source)
    if action=="format":
        return {"formatted":json.dumps(parsed,ensure_ascii=False,indent=2,allow_nan=False),
                "diagnostics":[]}
    limits = dict(max_vertices=max_vertices,max_edges=max_edges)
    if action in ("edit","collapse","workspace"):
        return _edit_action(action,request,parsed,limits,timeout)
    if action=="validate":
        model,warnings = prepare_model(parsed,input_format=input_format,adapter=converter,**limits)
        return {"model":model,"diagnostics":[asdict(item) for item in warnings]}
    options = options_from(request)
    algorithm,mode = request.get("algorithm","topology"),request.get("mode","balanced")
    if action=="elk-input":
        from src.layout.elk import elk_graph
        from src.layout.hybrid import analyze_graph
        model,_ = prepare_model(parsed,input_format=input_format,adapter=converter,**limits)
        if algorithm=="hybrid" and analyze_graph(model)["edges_per_vertex"]<2.7:
            return {"graph":None}
        return {"graph":elk_graph(model,options)}
    compare,rotate = request.get("compare",False),request.get("allowRotate",False)
    if (algorithm not in ("topology","legacy","advanced","hybrid","elk") or mode not in ("fast","balanced","quality")
            or type(compare) is not bool or type(rotate) is not bool):
        raise InputError("Unknown layout algorithm, mode or comparison setting.")
    if algorithm=="legacy":
        limits = dict(max_vertices=min(max_vertices,48),max_edges=min(max_edges,96))
    external = None
    if request.get("elkLayout") is not None:
        from src.layout.elk import elk_geometry
        def external(model,_remaining):
            return elk_geometry(model,options,request["elkLayout"])[0]
    if algorithm=="elk":
        if external is None:
            raise InputError("ELK is available in the browser with the optional runtime.")
        started = perf_counter()
        model,warnings = prepare_model(parsed,input_format=input_format,adapter=converter,**limits)
        geometry,quality = elk_geometry(model,options,request["elkLayout"])
        at_render = perf_counter()
        svg = render(model,geometry)
        at_end = perf_counter()
        elapsed = at_end-started
        if type(request.get("elkMs")) in (int,float) and 0<=request["elkMs"]<=60_000:
            elapsed += request["elkMs"]/1000
        quality.update(execution_ms=round(1000*(elapsed-(at_end-at_render)),3),
                       pipeline_ms=round(elapsed*1000,3),render_ms=round((at_end-at_render)*1000,3),
                       optimization={"mode":"elk","selected":"elk","candidates":[{"candidate":"elk","status":"valid"}],
                                     "reasons":["flat-elk-layout"]})
        response = {"model":model,"layout":geometry,"quality":quality,"svg":svg,
                    "diagnostics":[asdict(item) for item in warnings]}
    else:
        response = generated_response(generate(parsed,input_format=input_format,adapter=converter,options=options,algorithm=algorithm,
            mode=mode,timeout=timeout,allow_rotate=rotate,progress=progress,external_layout=external,
            external_name="elk" if external is not None else None,**limits))
    if request.get("elkWarning") and algorithm=="hybrid":
        response["diagnostics"].append({"severity":"warning","code":"elk-unavailable","path":"",
                                        "message":str(request["elkWarning"])[:300]})
    if compare and algorithm!="topology":
        if progress is not None:
            progress("compare")
        try:
            baseline = generate(response["model"],input_format="smd",options=options,algorithm="topology",
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


def execute_json(action, payload, progress=None, *, adapter=None):
    """Validate a bounded JSON message. User input is always data."""
    try:
        body = request_action(action,load_json(payload),progress=progress,adapter=adapter)
        status = 200
    except (ValueError,UnicodeError,RecursionError) as error:
        status,body = error_response(error)
    return json.dumps({"status":status,"body":body},ensure_ascii=False,allow_nan=False)
