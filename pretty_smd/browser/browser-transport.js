"use strict";

(() => {
  let worker = null;
  let next = 0;
  let pending = null;
  let ready = false;
  let observer = () => {};
  const root = new URL("./",document.currentScript.src);

  function failure(code,message,status=422) {
    return {ok:false,status,body:{diagnostics:[{severity:"error",code,path:"",message}]}};
  }
  function reset() {
    if (worker) worker.terminate();
    worker = null;
    ready = false;
  }
  function finish(result) {
    if (!pending) return;
    const current = pending;
    pending = null;
    clearTimeout(current.timer);
    current.resolve(result);
  }
  function abort(code,message,status) {
    reset();
    finish(failure(code,message,status));
  }
  function start() {
    worker = new Worker(new URL("engine-worker.js",root),{name:"pretty-smd-python"});
    const instance = worker;
    worker.onmessage = event => {
      const data = event.data;
      if (worker!==instance || !pending || pending.id!==data.id) return;
      if (data.type==="progress") {
        if (data.phase==="ready") ready = true;
        observer(data.phase);
      } else if (data.type==="fatal") {
        abort("worker-error",data.message,500);
      } else if (data.type==="result") {
        if (data.body.runtime) data.body.runtime.roundTripMs = performance.now()-pending.started;
        finish({ok:data.status===200,status:data.status,body:data.body});
      }
    };
    worker.onerror = () => {
      if (worker===instance) abort("worker-error","Python Worker 無法載入或已中止。",500);
    };
  }
  function request(action,payload,settings={}) {
    if (pending) abort("superseded","較新的操作已取代舊請求。",409);
    try {
      if (!worker) start();
    } catch (error) {
      return Promise.resolve(failure("worker-error",error.message,500));
    }
    return new Promise(resolve => {
      const id = ++next;
      const timeLimit = settings.timeoutMs ?? (ready ? 18000 : 65000);
      pending = {id,resolve,started:performance.now(),timer:setTimeout(() => {
        if (pending?.id===id) abort("worker-timeout","時間到。這次運算已中止，可以重試。",504);
      },timeLimit)};
      worker.postMessage({id,action,payload});
    });
  }
  window.prettySmdTransport = {
    request,
    examples:async () => {
      const response = await fetch(new URL("examples.json",root));
      if (!response.ok) throw new Error("無法載入內建案例。");
      return response.json();
    },
    listen(callback) { observer = callback; },
    cancel() { if (pending) abort("worker-cancelled","已取消運算。",499); },
  };
})();
