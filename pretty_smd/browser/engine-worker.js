"use strict";

importScripts("./runtime-config.js");
const config = self.PRETTY_RUNTIME;
const workerRoot = new URL("./",self.location.href);
let runtime;
let loaded;

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
  report(id,"dependencies");
  await python.loadPackage("jsonschema");
  report(id,"package");
  await python.loadPackage(new URL(config.wheel,workerRoot).href);
  python.runPython("from pretty_smd.bridge import execute_json");
  loaded = {initMs:performance.now()-start,...config};
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
    python.globals.set("_smd_action",action);
    python.globals.set("_smd_payload",JSON.stringify(payload));
    python.globals.set("_smd_progress",phase => report(id,phase));
    const before = performance.now();
    let result;
    try {
      result = JSON.parse(python.runPython("execute_json(_smd_action, _smd_payload, _smd_progress)"));
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
