// Smoke test using Apple's SafariDriver, separate from Playwright WebKit.
"use strict";

const assert = require("node:assert/strict");
const {spawn} = require("node:child_process");
const fs = require("node:fs/promises");
const http = require("node:http");
const path = require("node:path");
const {setTimeout: delay} = require("node:timers/promises");
const {openServer,siteURL} = require("./browser_runtime.cjs");

const output = path.resolve(process.argv[3] || "integration-output/safari");

async function availablePort() {
  const socket = http.createServer();
  await new Promise(resolve=>socket.listen(0,"127.0.0.1",resolve));
  const {port} = socket.address();
  await new Promise(resolve=>socket.close(resolve));
  return port;
}

async function main() {
  await fs.mkdir(output,{recursive:true});
  assert.equal(process.platform,"darwin","Apple Safari requires macOS.");
  const port = await availablePort();
  const base = "http://127.0.0.1:"+port;
  const server = await openServer();
  const driver = spawn("/usr/bin/safaridriver",["-p",String(port)],{stdio:"inherit"});
  let session;
  const report = {status:"failed",browser:"Apple Safari",url:siteURL()};
  async function command(method,route,body) {
    const response = await fetch(base+route,{method,body:body===undefined ? undefined : JSON.stringify(body),
      headers:{"Content-Type":"application/json"},signal:AbortSignal.timeout(80000)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.value?.message || "SafariDriver HTTP "+response.status);
    return data.value;
  }
  try {
    for (let i=0;i<40;i++) {
      try { await command("GET","/status"); break; }
      catch (error) {
        if (driver.exitCode!==null || i===39) throw error;
        await delay(250);
      }
    }
    session = await command("POST","/session",{capabilities:{alwaysMatch:{browserName:"safari"}}});
    report.version = session.capabilities.browserVersion;
    const prefix = "/session/"+session.sessionId;
    await command("POST",prefix+"/timeouts",{script:75000,pageLoad:60000});
    await command("POST",prefix+"/url",{url:report.url+"?lang=en"});
    const exercise = async callback => {
      let stage = "load the classroom examples";
      let rendered;
      const wait = async predicate => {
        const stop = performance.now()+65000;
        while (!predicate()) {
          if (performance.now()>stop) throw new Error(document.querySelector("#status")?.textContent || "UI timeout");
          await new Promise(resolve=>setTimeout(resolve,50));
        }
      };
      try {
        const button = document.querySelector('[data-lesson="resolvedBranch"]');
        await wait(()=>button && !button.disabled);
        stage = "generate the guarded example";
        button.click();
        await wait(()=>document.querySelector("#drawing svg") && !document.querySelector("#generate").disabled);
        stage = "select and generate Hybrid";
        const menu = document.querySelector("#algorithm");
        menu.value = "hybrid";
        menu.dispatchEvent(new Event("change",{bubbles:true}));
        document.querySelector("#generate").click();
        await wait(()=>!document.querySelector("#generate").disabled);
        const selection = document.querySelector("#selection");
        if (!selection || selection.hidden || !document.querySelector("#drawing svg"))
          throw new Error("Hybrid did not generate an SVG.");
        stage = "verify SVG and PNG";
        const {body,status} = await window.prettySmdTransport.request("generate",{
          source:document.querySelector("#source").value,algorithm:"hybrid"
        });
        if (status!==200 || !body.svg?.includes("<svg"))
          throw new Error(JSON.stringify(body.diagnostics));
        rendered = {svg:body.svg,engine:body.quality.optimization.selected,
          semantic:body.quality.semantic_preservation,userAgent:navigator.userAgent};
        const png = await window.pngFrom(body);
        const signature = Array.from(new Uint8Array(await png.slice(0,8).arrayBuffer()));
        callback({...rendered,signature});
      } catch (error) {
        let canvasEncoding;
        if (rendered) {
          try {
            const probe = document.createElement("canvas");
            probe.width = probe.height = 16;
            probe.getContext("2d",{willReadFrequently:true}).fillRect(0,0,16,16);
            canvasEncoding = probe.toDataURL("image/png").startsWith("data:image/png;base64,");
          } catch { canvasEncoding = false; }
        }
        callback({...rendered,failure:stage+": "+String(error),status:document.querySelector("#status")?.textContent,
          diagnostics:document.querySelector("#diagnostic-list")?.textContent,canvasEncoding});
      }
    };
    const result = await command("POST",prefix+"/execute/async",{script:"("+exercise.toString()+")(arguments[0]);",args:[]});
    if (result.svg) {
      await fs.writeFile(path.join(output,"safari.svg"),result.svg);
      Object.assign(report,{svgGenerated:true,engine:result.engine,userAgent:result.userAgent});
    }
    const screenshot = await command("GET",prefix+"/screenshot");
    await fs.writeFile(path.join(output,"safari.png"),Buffer.from(screenshot,"base64"));
    assert(!result.failure,JSON.stringify({failure:result.failure,status:result.status,
      diagnostics:result.diagnostics,canvasEncoding:result.canvasEncoding}));
    assert.equal(result.semantic,true);
    assert.deepEqual(result.signature,[137,80,78,71,13,10,26,10]);
    Object.assign(report,{status:"passed",pngSignature:result.signature});
  } catch(error) {
    report.message = error.message;
    throw error;
  } finally {
    await fs.writeFile(path.join(output,"safari.json"),JSON.stringify(report,null,2));
    if (session) await command("DELETE","/session/"+session.sessionId).catch(()=>{});
    driver.kill();
    server.close();
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
