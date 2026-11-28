// Real Pyodide acceptance against a plain static server, including the Pages subpath.
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const http = require("node:http");
const {spawnSync} = require("node:child_process");
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || "playwright");

const site = path.resolve(process.argv[2] || "dist");
const output = path.resolve(process.argv[3] || "integration-output/browser-runtime");
const prefix = "/pretty-state-machine-diagrams/";
const types = {".js":"text/javascript",".html":"text/html",".css":"text/css",
  ".wasm":"application/wasm",".json":"application/json",".svg":"image/svg+xml"};
let shell;

async function openServer() {
  const server = http.createServer(async (req,res) => {
    const url = new URL(req.url,"http://localhost");
    if (!url.pathname.startsWith(prefix) || req.method!=="GET") {res.writeHead(404).end();return;}
    const file = decodeURIComponent(url.pathname.slice(prefix.length));
    const abs = path.resolve(site,file.endsWith("/") || !file ? file+"index.html" : file);
    if (!abs.startsWith(site+path.sep)) {res.writeHead(404).end();return;}
    try {
      const body = await fs.readFile(abs);
      const mime = types[path.extname(abs)] || "application/octet-stream";
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

  for (const [type,filename] of [["svg","diagram.svg"],["png","diagram.png"]]) {
    await page.locator("#export").selectOption(type);
    const [download] = await Promise.all([page.waitForEvent("download"),page.locator("#download").click()]);
    assert.equal(download.suggestedFilename(),filename);
    const content = await fs.readFile(await download.path());
    if (type==="png") assert.equal(content.subarray(0,8).toString("hex"),"89504e470d0a1a0a");
    else assert.match(content.toString("utf8"),/<svg/);
  }
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

(async () => {
  await fs.mkdir(output,{recursive:true});
  const server = process.env.P57_LIVE ? null : await openServer();
  if (process.env.P57_LIVE) shell = new URL("./",process.env.P57_LIVE.replace(/\/?$/,"/")).href;
  let browser;
  try {
    browser = await chromium.launch({headless:true,executablePath:process.env.CHROME||undefined});
    const cold = await smoke(browser);
    console.log("Runtime",JSON.stringify(cold));
    if (!process.env.P57_SMOKE_ONLY) await parity(browser,Boolean(process.env.P57_STRESS));
  } finally {
    if (browser) await browser.close();
    if (server) server.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
