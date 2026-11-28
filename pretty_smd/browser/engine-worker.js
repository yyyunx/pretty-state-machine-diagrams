"use strict";

importScripts("./runtime-config.js");
const config = self.PRETTY_RUNTIME;
const workerRoot = new URL("./",self.location.href);
let runtime;
let loaded;
let elk;

function report(id,phase) {
  self.postMessage({id,type:"progress",phase});
}

async function initialize(id) {
  report(id,"initializing");
  const start = performance.now();
  const indexURL = new URL(config.runtime,workerRoot).href;
  report(id,"runtime");
  importScripts(new URL("pyodide.js",indexURL).href);
  const python = await loadPyodide({indexURL});
  const runtimeReady = performance.now();
  report(id,"packages");
  // Resolve the pinned dependency tree and project wheel in one load so
  // the same-origin wheel can transfer while the dependencies are loading.
  await python.loadPackage(["jsonschema",new URL(config.wheel,workerRoot).href]);
  const packagesReady = performance.now();
  report(id,"imports");
  python.runPython("from pretty_smd.bridge import execute_json");
  const imported = performance.now();
  loaded = {initMs:imported-start,initStagesMs:{runtime:runtimeReady-start,
    packages:packagesReady-runtimeReady,imports:imported-packagesReady},...config};
  return python;
}

self.onmessage = async event => {
  const {id,action,payload} = event.data;
  const started = performance.now();
  try {
    const cold = !runtime;
    runtime ??= initialize(id);
    const python = await runtime;
    report(id,"ready");
    if (action==="initialize") {
      self.postMessage({id,type:"result",status:200,body:{engine:loaded,cold}});
      return;
    }
    python.globals.set("_smd_progress",phase => report(id,phase));
    const before = performance.now();
    let result;
    try {
      const execute = (operation,data) => {
        python.globals.set("_smd_action",operation);
        python.globals.set("_smd_payload",JSON.stringify(data));
        return JSON.parse(python.runPython("execute_json(_smd_action, _smd_payload, _smd_progress)"));
      };
      if (action==="generate" && (payload.algorithm==="elk" || (payload.algorithm==="hybrid" && payload.useElk))) {
        const prepared = execute("elk-input",payload);
        if (prepared.status!==200 && payload.algorithm==="elk") {
          result = prepared;
        } else if (prepared.status!==200) {
          payload.elkWarning = prepared.body.diagnostics?.[0]?.message || "ELK rejected the model.";
        } else if (prepared.body.graph) {
          try {
            report(id,"elk");
            if (!elk) {
              const base = new URL(config.elk,workerRoot);
              importScripts(new URL("elk-api.js",base).href);
              elk = new self.ELK({workerUrl:new URL("elk-worker.min.js",base).href,algorithms:["layered"]});
            }
            const started = performance.now();
            payload.elkLayout = await elk.layout(prepared.body.graph);
            payload.elkMs = performance.now()-started;
          } catch (error) {
            payload.elkWarning = String(error.message || error);
            if (payload.algorithm==="elk") result = {status:422,body:{diagnostics:[{
              severity:"error",code:"elk-error",path:"",message:payload.elkWarning,
            }]}};
          }
        }
      }
      result ??= execute(action,payload);
    } finally {
      for (const key of ["_smd_action","_smd_payload","_smd_progress"]) python.globals.delete(key);
    }
    const measured = {engineMs:performance.now()-before,workerMs:performance.now()-started,
                      wasmHeapBytes:python._module?.HEAPU8?.byteLength ?? null,cold,
                      ...loaded};
    result.body.runtime = measured;
    self.postMessage({id,type:"result",...result});
  } catch(error) {
    self.postMessage({id,type:"fatal",message:String(error.message || error)});
  }
};
