// Real Pyodide acceptance against a plain static server, including the Pages subpath.
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const http = require("node:http");
const {spawnSync} = require("node:child_process");
const playwright = require(process.env.PLAYWRIGHT_MODULE || "playwright");

const site = path.resolve(process.argv[2] || "dist");
let serving = site;
const output = path.resolve(process.argv[3] || "integration-output/browser-runtime");
const prefix = "/pretty-state-machine-diagrams/";
const target = process.env.P57_BROWSER || "chromium";
const delay = Number(process.env.P57_REQUEST_DELAY_MS || 0);
const types = {".js":"text/javascript",".html":"text/html",".css":"text/css",
  ".wasm":"application/wasm",".json":"application/json",".svg":"image/svg+xml"};
let shell;
let originDisconnected = false;

async function openServer() {
  const server = http.createServer(async (req,res) => {
    if (originDisconnected) {res.destroy();return;}
    const url = new URL(req.url,"http://localhost");
    if (!url.pathname.startsWith(prefix) || req.method!=="GET") {res.writeHead(404).end();return;}
    const file = decodeURIComponent(url.pathname.slice(prefix.length));
    const abs = path.resolve(serving,file.endsWith("/") || !file ? file+"index.html" : file);
    if (!abs.startsWith(serving+path.sep)) {res.writeHead(404).end();return;}
    try {
      const body = await fs.readFile(abs);
      const mime = types[path.extname(abs)] || "application/octet-stream";
      if (delay && /^(runtime|engine)\//.test(file)) await new Promise(resolve=>setTimeout(resolve,delay));
      res.writeHead(200,{"Content-Type":mime,"Content-Length":body.length});
      res.end(body);
    } catch {
      res.writeHead(404).end();
    }
  });
  await new Promise(resolve => server.listen(0,"127.0.0.1",resolve));
  shell = "http://127.0.0.1:" + server.address().port + prefix;
  return server;
}

function exact(actual,expected,where="root") {
  if (typeof expected==="number") {
    assert(typeof actual==="number" && Math.abs(actual-expected)<1e-5,where+" "+actual+" ≠ "+expected);
  } else if (Array.isArray(expected)) {
    assert(Array.isArray(actual),where);
    assert.equal(actual.length,expected.length,where);
    for (let i=0;i<expected.length;i++) exact(actual[i],expected[i],where+"["+i+"]");
  } else if (expected && typeof expected==="object") {
    assert.deepEqual(Object.keys(actual).sort(),Object.keys(expected).sort(),where);
    for (const key of Object.keys(expected)) exact(actual[key],expected[key],where+"/"+key);
  } else {
    assert.equal(actual,expected,where);
  }
}

function geometryMetric(report) {
  const result = {...report};
  delete result.execution_ms; delete result.render_ms; delete result.pipeline_ms;
  if (result.optimization) {
    result.optimization = {...result.optimization,
      candidates:result.optimization.candidates.map(({elapsed_ms,...candidate})=>candidate)};
  }
  return result;
}

async function svgStructure(page,svg) {
  return page.evaluate(svg => {
    const doc = new DOMParser().parseFromString(svg,"image/svg+xml");
    const numeric = new Set(["width","height","x","y","cx","cy","r","x1","x2","y1","y2",
      "viewBox","points","rx","ry","refX","refY","markerWidth","markerHeight","stroke-width",
      "font-size","dy"]);
    const visit = node => [node.localName,[...node.attributes].sort((a,b)=>a.name.localeCompare(b.name))
      .map(({name,value})=>[name,numeric.has(name)
        ? value.split(/[\s,]+/).filter(Boolean).map(v=>Number.isFinite(Number(v))?Number(v):v) : value]),
      [...node.childNodes].flatMap(child=>child.nodeType===1 ? [visit(child)]
        : child.nodeType===3 && (child.nodeValue.trim() || ["text","tspan"].includes(node.localName))
          ? [child.nodeValue] : [])];
    return visit(doc.documentElement);
  },svg);
}

async function request(page,action,payload,settings) {
  return page.evaluate(({action,payload,settings}) => window.prettySmdTransport.request(action,payload,settings),
    {action,payload,settings});
}

function vectors(stress) {
  const result = spawnSync(process.env.PYTHON || "python",["-m","tests.browser_vectors",...(stress?["--stress"]:[])],
    {cwd:path.resolve(__dirname,".."),encoding:"utf8",maxBuffer:60*1024*1024,timeout:180000});
  assert.equal(result.status,0,result.stderr || String(result.error));
  return JSON.parse(result.stdout);
}

async function smoke(browser) {
  const page = await browser.newPage({viewport:{width:1440,height:1050},acceptDownloads:true});
  const remote = [];
  const errors = [];
  page.on("pageerror",error=>errors.push(error.message));
  page.on("request",req=>remote.push(req.url()));
  await page.goto(shell);
  await page.waitForFunction(()=>document.querySelector("#source").value.includes("resolvedBehavior"));
  assert(!remote.some(url=>url.includes("/runtime/")));
  const boot = await request(page,"initialize",{});
  assert.equal(boot.status,200,JSON.stringify(boot.body));
  assert.equal(boot.body.engine.version,"0.29.3");
  await page.locator("#generate").click();
  await page.locator("#drawing svg").waitFor();
  await page.locator("#algorithm").selectOption("advanced");
  await page.locator("#mode").selectOption("balanced");
  await page.locator("#generate").click();
  await page.locator("#comparison").waitFor();
  await page.screenshot({path:path.join(output,"browser-app.png"),fullPage:true});

  for (const [type,filename] of [["svg","diagram.svg"],["png","diagram.png"],["model","diagram.model.json"],
    ["layout","diagram.layout.json"],["quality","diagram.quality.json"]]) {
    await page.locator("#export").selectOption(type);
    const [download] = await Promise.all([page.waitForEvent("download"),page.locator("#download").click()]);
    assert.equal(download.suggestedFilename(),filename);
    const content = await fs.readFile(await download.path());
    if (type==="png") assert.equal(content.subarray(0,8).toString("hex"),"89504e470d0a1a0a");
    else if (type==="svg") assert.match(content.toString("utf8"),/<svg/);
    else {
      const parsed = JSON.parse(content.toString("utf8"));
      if (type==="model") assert.equal(parsed.schemaVersion,"0.1.0-draft");
      if (type==="layout") assert(Object.keys(parsed.edges).length>0);
      if (type==="quality") assert.equal(parsed.semantic_preservation,true);
    }
  }
  await page.locator("#settings summary").click();
  const [settings] = await Promise.all([page.waitForEvent("download"),page.locator("#save-settings").click()]);
  assert.equal(settings.suggestedFilename(),"pretty-smd.settings.json");
  const savedSettings = await fs.readFile(await settings.path());
  assert.equal(JSON.parse(savedSettings).algorithm,"advanced");
  await page.locator("#algorithm").selectOption("topology");
  await page.locator("#load-settings").setInputFiles({name:"settings.json",mimeType:"application/json",buffer:savedSettings});
  await page.waitForFunction(()=>document.querySelector("#algorithm").value==="advanced");
  const seeded = await request(page,"validate",{source:'{"id":"dup","id":"dup2"}'});
  assert.equal(seeded.status,422);
  assert.match(seeded.body.diagnostics[0].message,/Duplicate JSON/);
  const interrupted = await page.evaluate(async () => {
    const engine = window.prettySmdTransport;
    const payload = {source:document.querySelector("#source").value,algorithm:"advanced",mode:"quality"};
    const work = engine.request("generate",payload);
    engine.cancel();
    return work;
  });
  assert.equal(interrupted.status,499);
  assert.equal((await request(page,"initialize",{},{timeoutMs:1})).status,504);
  assert.equal((await request(page,"initialize",{})).status,200);
  await page.goto(shell+"gallery/");
  await page.locator("#edit-case").click();
  await page.waitForFunction(()=>new URLSearchParams(location.search).has("case") &&
    document.querySelector("#source").value.length>10);
  await page.locator("#generate").click();
  await page.locator("#drawing svg").waitFor({timeout:60000});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert(remote.every(url=>url.startsWith(shell) && !url.includes("/api/") || url.startsWith("blob:")));
  assert.deepEqual(errors,[]);
  await page.close();
  return boot.body.engine;
}

async function responsive(browser) {
  for (const [name,viewport] of [["phone",{width:390,height:844}],["tablet",{width:820,height:1180}]]) {
    const context = await browser.newContext({viewport,hasTouch:true,isMobile:target!=="firefox"});
    try {
      const page = await context.newPage();
      await page.goto(shell);
      await page.locator('[data-lesson="resolvedBranch"]').tap();
      await page.locator("#drawing svg").waitFor({timeout:65000});
      assert.equal(await page.locator("#example").inputValue(),"resolvedBranch");
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      const before = await page.locator("#drawing").getAttribute("style");
      await page.locator("#zoom-in").tap();
      assert.notEqual(await page.locator("#drawing").getAttribute("style"),before);
      await page.locator("#fit").tap();
      await page.screenshot({path:path.join(output,name+".png"),fullPage:true});
    } finally { await context.close(); }
  }
}

async function profile(browser) {
  const samples = [];
  const baseline = process.env.P57_PROFILE_BASELINE;
  if (baseline && process.env.P57_LIVE) throw new Error("Paired profiling requires a local test server.");
  for (let pair=0;pair<Number(process.env.P57_PROFILE_ONLY);pair++) {
    const order = !baseline ? ["candidate"] : pair%2 ? ["candidate","baseline"] : ["baseline","candidate"];
    for (const variant of order) {
      serving = variant==="baseline" ? path.resolve(baseline) : site;
      const page = await browser.newPage();
      try {
        await page.goto(shell);
        await page.waitForFunction(()=>document.querySelector("#source").value.length>10);
        const payload = {source:await page.locator("#source").inputValue()};
        const cold = await request(page,"generate",payload);
        const warm = await request(page,"generate",payload);
        assert.equal(cold.status,200,JSON.stringify(cold.body.diagnostics));
        assert.equal(warm.status,200,JSON.stringify(warm.body.diagnostics));
        assert.equal(cold.body.runtime.cold,true);
        assert.equal(warm.body.runtime.cold,false);
        samples.push({pair,variant,cold:cold.body.runtime.roundTripMs,warm:warm.body.runtime.roundTripMs,
          init:cold.body.runtime.initMs,stages:cold.body.runtime.initStagesMs});
      } finally { await page.close(); }
    }
  }
  await fs.writeFile(path.join(output,"startup.json"),JSON.stringify({browser:browser.version(),delay,samples},null,2));
}

async function parity(browser,withStress) {
  const page = await browser.newPage();
  await page.goto(shell);
  const samples = vectors(false);
  const report = [];
  for (const vector of samples) {
    const result = await request(page,"generate",vector.payload,{timeoutMs:45000});
    const where = vector.case+" "+vector.payload.algorithm+" "+vector.payload.mode;
    assert.equal(vector.expected.status,200,where+" native");
    assert.equal(result.status,200,where+" "+JSON.stringify(result.body.diagnostics));
    exact(result.body.model,vector.expected.body.model,where+"/model");
    exact(result.body.layout,vector.expected.body.layout,where+"/layout");
    exact(geometryMetric(result.body.quality),geometryMetric(vector.expected.body.quality),where+"/quality");
    exact(await svgStructure(page,result.body.svg),await svgStructure(page,vector.expected.body.svg),where+"/svg");
    report.push({case:vector.case,algorithm:vector.payload.algorithm,mode:vector.payload.mode,
      native_ms:vector.expected.elapsedMs,browser:result.body.runtime,quality:result.body.quality});
    console.log("Parity",where);
  }
  await fs.writeFile(path.join(output,"parity.json"),JSON.stringify(report,null,2));
  const names = ["linear","cycle","self-loop","multilingual","holdout-dense-17","orthogonal"];
  const external = await page.evaluate(async names=>{
    const api = window.prettySmdTransport;
    const all = await api.examples();
    const results = [];
    for (const name of names) for (const [algorithm,useElk] of [["elk",true],["hybrid",true]]) {
      if (!all["gallery-"+name]) continue;
      let frames = 0, timer;
      const count = ()=>{frames++;timer=requestAnimationFrame(count);};
      timer = requestAnimationFrame(count);
      const response = await api.request("generate",{source:JSON.stringify(all["gallery-"+name]),algorithm,useElk});
      cancelAnimationFrame(timer);
      const {quality,runtime,diagnostics} = response.body;
      results.push({case:name,algorithm,status:response.status,frames,quality,runtime,diagnostics});
    }
    return results;
  },names);
  const rejected = external.find(row=>row.case==="orthogonal" && row.algorithm==="elk");
  assert.equal(rejected?.status,422);
  assert.match(rejected.diagnostics[0].message,/supports a flat/);
  await fs.writeFile(path.join(output,"external.json"),JSON.stringify(external,null,2));
  if (withStress) {
    const rows = [];
    for (const vector of vectors(true)) {
      const start = Date.now();
      const result = await request(page,"generate",vector.payload,{timeoutMs:18000});
      const elapse = Date.now()-start;
      rows.push({case:vector.case,algorithm:vector.payload.algorithm,mode:vector.payload.mode,
        native:{status:vector.expected.status,elapsed_ms:vector.expected.elapsedMs,
                quality:vector.expected.body.quality,diagnostics:vector.expected.body.diagnostics},
        browser:{status:result.status,elapsed_ms:elapse,runtime:result.body.runtime,
                 quality:result.body.quality,diagnostics:result.body.diagnostics}});
      console.log("Stress",vector.case,vector.payload.algorithm,vector.payload.mode,result.status);
      await fs.writeFile(path.join(output,"stress.json"),JSON.stringify(rows,null,2));
    }
  }
  await page.close();
}

async function editor(browser) {
  const context = await browser.newContext({viewport:{width:1450,height:1060},acceptDownloads:true});
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror",error=>errors.push(error.message));
  await page.goto(shell+"?case=linear&lang=en");
  await page.waitForFunction(()=>document.querySelector("#source").value.length>10);
  assert.equal(await page.locator("#generate").textContent(),"Generate diagram");
  const initialSource = await page.locator("#source").inputValue();
  const elk = await request(page,"generate",{source:initialSource,algorithm:"elk"});
  assert.equal(elk.status,200,JSON.stringify(elk.body.diagnostics));
  assert.equal(elk.body.quality.optimization.selected,"elk");
  await fs.writeFile(path.join(output,"linear-elk.svg"),elk.body.svg);

  await page.locator("#generate").click();
  await page.locator("#drawing svg").waitFor();
  const initial = await page.evaluate(()=>({model:current.model,layout:current.layout,quality:current.quality}));
  const id = initial.model.regions[0].vertices.find(item=>item.kind==="state").id;
  const node = page.locator('[data-node-id="'+id+'"]');
  await page.locator("#edit-mode").check();
  await node.scrollIntoViewIfNeeded();
  const pos = await node.boundingBox();
  await page.evaluate(()=>{
    document.querySelector("#canvas").addEventListener("pointerdown",event=>{
      window._pointer = [event.target.localName,event.target.closest("[data-node-id]")?.outerHTML.slice(0,150),
        event.target.getAttribute("data-edge-id")];
    },{once:true,capture:true});
  });
  await page.mouse.move(pos.x+pos.width/2,pos.y+pos.height/2);
  await page.mouse.down();
  const started = await page.evaluate(()=>({drag,enabled:!document.querySelector("#edit-mode").disabled,
    checked:document.querySelector("#edit-mode").checked,hit:window._pointer}));
  assert.equal(started.drag?.id,id,JSON.stringify(started));
  await page.mouse.move(pos.x+pos.width/2,pos.y+pos.height/2+Math.min(15,pos.height*.3),{steps:5});
  const preview = await page.evaluate(()=>({point:drag?.next,ghost:!!document.querySelector(".node-ghost")}));
  assert(preview.ghost && preview.point,JSON.stringify(preview));
  await page.mouse.up();
  await page.waitForFunction(()=>document.querySelector("#edit-status").textContent.length>0,{},{timeout:12000})
    .catch(async error=>{
      await page.screenshot({path:path.join(output,"editor-failure.png"),fullPage:true});
      const state = await page.evaluate(({x,y})=>({target:document.elementFromPoint(x,y)?.outerHTML.slice(0,300),
        busy,canvas:document.querySelector("#canvas").getBoundingClientRect().toJSON()}),
      {x:pos.x+pos.width/2,y:pos.y+pos.height/2});
      throw new Error(error.message+" "+JSON.stringify({pos,state,errors}));
    });
  assert.match(await page.locator("#edit-status").textContent(),/Rerouted/);
  const moved = await page.evaluate(()=>({model:current.model,layout:current.layout,edit:current.edit,quality:current.quality}));
  exact(moved.model,initial.model);
  assert.notEqual(moved.layout.nodes[id].bounds.y,initial.layout.nodes[id].bounds.y);
  assert.equal(moved.edit.unaffected_displacement,0);
  for (const [key,part] of Object.entries(initial.layout.nodes)) if (key!==id) exact(moved.layout.nodes[key],part);
  await page.locator("#toggle-lock").click();
  assert(await node.evaluate(item=>item.classList.contains("locked-node")));
  await page.locator("#generate").click();
  await page.waitForFunction(()=>!document.querySelector("#generate").disabled);
  const relaid = await page.evaluate(id=>current.layout.nodes[id].bounds,id);
  exact(relaid,moved.layout.nodes[id].bounds,"locked node after automatic layout");
  await page.locator("#undo").click();
  await page.keyboard.press("Control+z");
  assert(!(await node.evaluate(item=>item.classList.contains("locked-node"))));
  await page.locator("#redo").click();
  assert(await node.evaluate(item=>item.classList.contains("locked-node")));

  await page.locator("#example").selectOption("nested");
  await page.locator("#algorithm").selectOption("hybrid");
  await page.locator("#generate").click();
  await page.waitForFunction(()=>current?.quality.optimization?.features.hierarchy_depth>0);
  const nested = await page.evaluate(()=>({model:current.model,layout:current.layout,
    composite:current.model.regions[0].vertices.find(item=>item.kind==="composite").id}));
  await page.locator('[data-node-id="'+nested.composite+'"]').press("Enter");
  await page.locator("#toggle-collapse").click();
  await page.waitForFunction(()=>document.querySelector("#edit-status").textContent.includes("Hidden internal nodes"));
  assert(await page.locator("#drawing [data-node-id]").count()<Object.keys(nested.layout.nodes).length);
  exact(await page.evaluate(()=>current.model),nested.model);
  const projection = await page.evaluate(()=>({summary:projection.summary,svg:projection.svg,full:current.svg}));
  assert(Object.values(projection.summary)[0].vertices>0);
  await fs.writeFile(path.join(output,"nested-hybrid.svg"),projection.full);
  await fs.writeFile(path.join(output,"nested-collapsed.svg"),projection.svg);
  await page.screenshot({path:path.join(output,"editor.png"),fullPage:true});
  await page.locator("#toggle-collapse").click();
  await page.waitForFunction(()=>projection===null);
  assert.equal(await page.locator("#drawing [data-node-id]").count(),Object.keys(nested.layout.nodes).length);

  await page.locator("#workspace summary").click();
  await page.locator("#auto-save").check();
  const [download] = await Promise.all([page.waitForEvent("download"),page.locator("#workspace-save").click()]);
  assert.equal(download.suggestedFilename(),"diagram.workspace.json");
  const workspace = await fs.readFile(await download.path());
  await fs.writeFile(path.join(output,"nested.workspace.json"),workspace);
  assert(workspace.includes(Buffer.from(nested.composite)));
  await page.reload();
  await page.locator("#workspace summary").click();
  await page.locator("#workspace-restore").click();
  await page.waitForFunction(()=>document.querySelector("#edit-status").textContent==="Workspace loaded.");
  exact(await page.evaluate(()=>current.model),nested.model);
  await page.locator("#workspace-clear").click();
  assert(await page.locator("#workspace-restore").isDisabled());
  await page.locator("#workspace-file").setInputFiles({name:"project.json",mimeType:"application/json",buffer:workspace});
  await page.waitForFunction(()=>!document.querySelector("#workspace-file").disabled);
  exact(await page.evaluate(()=>current.layout),nested.layout);
  await page.locator("#offline-download").click();
  await page.waitForFunction(()=>!!navigator.serviceWorker.controller,{},{timeout:90000});
  // Disconnect the test origin itself. This is independent of how the
  // browser reports navigator.onLine and still exercises the service worker.
  const cutOrigin = !process.env.P57_LIVE;
  const liveWebKit = target==="webkit" && Boolean(process.env.P57_LIVE);
  if (cutOrigin) originDisconnected = true;
  else if (!liveWebKit) await context.setOffline(true);
  try {
    if (!liveWebKit) {
      const disconnected = await page.evaluate(async ()=>{
        try {
          await fetch("./offline-origin-check-"+Date.now(),{cache:"no-store"});
          return false;
        } catch { return true; }
      });
      assert(disconnected,"An uncached request must fail while the origin is disconnected.");
    }
    await page.reload();
    await page.waitForFunction(()=>document.querySelector("#source").value.length>10);
    await page.locator("#generate").click();
    await page.locator("#drawing svg").waitFor({timeout:60000});
  } finally {
    originDisconnected = false;
    if (!cutOrigin && !liveWebKit) await context.setOffline(false);
  }
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,"incremental.json"),JSON.stringify({initial:initial.quality,edited:moved.quality,
    edit:moved.edit},null,2));
  await context.close();
}

async function main() {
  await fs.mkdir(output,{recursive:true});
  const server = process.env.P57_LIVE ? null : await openServer();
  if (process.env.P57_LIVE) shell = new URL("./",process.env.P57_LIVE.replace(/\/?$/,"/")).href;
  let browser;
  try {
    const engine = target==="edge" ? playwright.chromium : playwright[target];
    if (!["chromium","firefox","webkit","edge"].includes(target)) throw new Error("Unknown P57_BROWSER: "+target);
    const launch = {headless:true};
    if (target==="edge") launch.channel = "msedge";
    if (target==="chromium" && process.env.CHROME) launch.executablePath = process.env.CHROME;
    browser = await engine.launch(launch);
    console.log("Browser",target,browser.version());
    if (process.env.P57_PROFILE_ONLY) { await profile(browser); return; }
    let boot = null;
    if (!process.env.P57_BENCHMARK_ONLY) {
      if (!process.env.P57_EDITOR_ONLY) {
        boot = await smoke(browser);
        console.log("Runtime",JSON.stringify(boot));
      }
      await editor(browser);
      await responsive(browser);
      console.log("ELK, Hybrid, editor, workspace and offline passed.");
    }
    if (!process.env.P57_SMOKE_ONLY) await parity(browser,Boolean(process.env.P57_STRESS));
    await fs.writeFile(path.join(output,"acceptance.json"),JSON.stringify({
      target,browser:browser.version(),url:shell,boot,
      editor:!process.env.P57_BENCHMARK_ONLY,phone:!process.env.P57_BENCHMARK_ONLY,tablet:!process.env.P57_BENCHMARK_ONLY,
      offlineMethod:!process.env.P57_LIVE ? "test origin disconnected" :
        target==="webkit" ? "cache and online reload" : "Playwright offline context"
    },null,2));
  } finally {
    if (browser) await browser.close();
    if (server) server.close();
  }
}

if (require.main===module) main().catch(error=>{console.error(error);process.exitCode=1;});
module.exports = {openServer,siteURL:()=>shell};
