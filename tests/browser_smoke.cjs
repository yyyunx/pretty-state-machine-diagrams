// Run with Playwright and Chromium, optionally supplying CHROME and PYTHON.
"use strict";

const assert = require("node:assert/strict");
const {spawn} = require("node:child_process");
const fs = require("node:fs/promises");
const path = require("node:path");
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || "playwright");

const root = path.resolve(__dirname, "..");
const output = path.resolve(process.argv[2] || "integration-output/browser");
const base = "http://127.0.0.1:" + (process.env.PRETTY_SMD_TEST_PORT || "8765");
const artifacts = process.env.PRETTY_SMD_BENCHMARK || path.join(root, "benchmarks");

async function start(args,address) {
  const child = spawn(process.env.PYTHON || "python", args,
    {cwd: root, windowsHide: true, stdio: "inherit"});
  try {
    for (let attempt = 0; attempt < 80; attempt++) {
      if (child.exitCode !== null) throw new Error("Local server exited.");
      try {
        const response = await fetch(address);
        await response.arrayBuffer();
        if (response.ok) return child;
      } catch {}
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error("Local server did not start.");
  } catch (error) {
    child.kill();
    throw error;
  }
}

async function checkGallery(browser,directory) {
  const port = Number(new URL(base).port)+1;
  const address = "http://127.0.0.1:" + port;
  const server = await start(["-m","http.server",String(port),"--bind","127.0.0.1",
    "--directory",path.resolve(directory)],address);
  const page = await browser.newPage({viewport:{width:1440,height:1050}});
  try {
    await page.goto(address);
    await page.waitForFunction(() => Array.from(document.images).every(img => img.complete && img.naturalWidth>0));
    await page.waitForFunction(() => document.querySelector("#bench-status").textContent.includes("量測"));
    await page.locator("#case").selectOption("self-loop");
    await page.waitForFunction(() => Array.from(document.querySelectorAll("#figures img")).every(
      img => img.src.endsWith("/self-loop.svg") && img.complete && img.naturalWidth>0));
    await page.locator("#zoom").evaluate(field => {
      field.value = 200;
      field.dispatchEvent(new Event("input"));
    });
    assert.equal(await page.locator("#zoom-value").textContent(),"200%");
    await page.locator("#reset").click();
    assert.equal(await page.locator("#zoom-value").textContent(),"100%");
    await page.screenshot({path:path.join(output,"gallery.png"),fullPage:true});
  } finally {
    await page.close();
    server.kill();
  }
}

async function checkApp(browser) {
  const page = await browser.newPage({viewport:{width:1440,height:940}, acceptDownloads:true});
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(base);
  await page.locator("#drawing svg").waitFor();
  await page.screenshot({path:path.join(output,"web-app.png")});
  const horizontal = await page.locator("#drawing svg").getAttribute("viewBox");
  const transform = () => page.locator("#drawing").evaluate(item => item.style.transform);
  const initial = await transform();
  await page.locator("#zoom-in").click();
  assert.notEqual(await transform(), initial);
  await page.locator("#fit").click();
  assert.equal(await transform(), initial);
  await page.locator("#reset").click();
  const reset = await transform();
  const box = await page.locator("#canvas").boundingBox();
  await page.mouse.move(box.x+10, box.y+10);
  await page.mouse.down();
  await page.mouse.move(box.x+70, box.y+50, {steps:4});
  await page.mouse.up();
  assert.notEqual(await transform(), reset);
  await page.locator("#fullscreen").click();
  await page.waitForFunction(() => document.fullscreenElement?.id === "viewer");
  await page.locator("#fullscreen").click();
  await page.waitForFunction(() => !document.fullscreenElement);

  await page.locator("#direction").selectOption("vertical");
  const [response] = await Promise.all([
    page.waitForResponse(response => response.url().endsWith("/api/generate")),
    page.locator("#generate").click(),
  ]);
  const result = await response.json();
  assert.equal(response.status(), 200, JSON.stringify(result.diagnostics));
  await page.waitForFunction(before => document.querySelector("#drawing svg").getAttribute("viewBox") !== before, horizontal);
  await page.locator("#drawing [data-node-id][tabindex]").last().press("Enter");
  assert.match(await page.locator("#item").textContent(), /"種類"/);
  await page.locator("#drawing [data-edge-id][tabindex]").first().press("Enter");
  assert.match(await page.locator("#item").textContent(), /"Trigger"/);
  for (const [kind, key] of Object.entries({svg:"svg", model:"model", layout:"layout", quality:"quality"})) {
    await page.locator("#export").selectOption(kind);
    const [download] = await Promise.all([page.waitForEvent("download"), page.locator("#download").click()]);
    const contents = await fs.readFile(await download.path(), "utf8");
    if (kind === "svg") assert.equal(contents, result[key]);
    else assert.deepEqual(JSON.parse(contents), result[key]);
  }

  await page.locator("#file").setInputFiles(path.join(root, "examples", "basic.smd.json"));
  await page.waitForFunction(() => document.querySelector("#source").value.includes("待機"));
  const [upload] = await Promise.all([
    page.waitForResponse(response => response.url().endsWith("/api/generate")),
    page.locator("#generate").click(),
  ]);
  assert.equal(upload.status(), 200);
  await page.locator("#source").fill("{");
  await page.locator("#generate").click();
  await page.locator("#diagnostic-list li").first().waitFor();
  assert.match(await page.locator("#diagnostic-list").textContent(), /Invalid JSON/);
  await page.locator("#format").selectOption("pa");
  assert.equal(await page.locator("#generate").isDisabled(), true);
  assert.equal(await page.locator("#pa-note").isVisible(), true);
  await page.locator("#theme").click();
  assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.deepEqual(errors, []);
  await page.close();
}

async function checkAdvanced(browser) {
  const page = await browser.newPage({viewport:{width:1440,height:1080},acceptDownloads:true});
  const errors = [];
  page.on("pageerror",error => errors.push(error.message));
  await page.goto(base);
  await page.locator("#drawing svg").waitFor();
  await page.locator("#example").selectOption("pseudostates");
  await page.locator("#algorithm").selectOption("advanced");
  await page.locator("#mode").selectOption("balanced");
  const [response] = await Promise.all([
    page.waitForResponse(response => response.url().endsWith("/api/generate")),
    page.locator("#generate").click(),
  ]);
  const result = await response.json();
  assert.equal(response.status(),200,JSON.stringify(result.diagnostics));
  await page.locator("#comparison").waitFor();
  assert.equal(result.baseline.quality.edge_crossings,2);
  assert.equal(result.quality.edge_crossings,1);
  await page.locator("#before").click();
  assert.equal(await page.locator("#before").getAttribute("aria-pressed"),"true");
  const [download] = await Promise.all([page.waitForEvent("download"),page.locator("#download").click()]);
  assert.equal(await fs.readFile(await download.path(),"utf8"),result.baseline.svg);
  await page.locator("#after").click();
  await page.locator("#hierarchy > summary").click();
  await page.locator("#search").fill("Active");
  await page.locator("#tree").getByRole("button",{name:"Active",exact:true}).click();
  assert.match(await page.locator("#item").textContent(),/Active/);
  assert(await page.locator("#drawing polyline.related-edge").count() > 0);
  await page.screenshot({path:path.join(output,"advanced-app.png"),fullPage:true});
  await page.locator("#settings > summary").click();
  const [settings] = await Promise.all([page.waitForEvent("download"),page.locator("#save-settings").click()]);
  const backup = await fs.readFile(await settings.path());
  assert.equal(JSON.parse(backup).mode,"balanced");
  await page.locator("#mode").selectOption("quality");
  await page.locator("#load-settings").setInputFiles({name:"settings.json",mimeType:"application/json",buffer:backup});
  await page.waitForFunction(() => document.querySelector("#mode").value==="balanced");

  await page.locator("#example").selectOption("benchmark-sparse");
  await page.locator("#mode").selectOption("fast");
  await page.locator("#compare").uncheck();
  await page.locator("#generate").click();
  await page.locator("#minimap").waitFor();
  const window = page.locator("#mini-window");
  const before = await window.getAttribute("x");
  await page.locator("#mini-svg").click({position:{x:15,y:28}});
  assert.notEqual(await window.getAttribute("x"),before);
  await page.locator("#mini-fit").click();
  assert.equal(await window.getAttribute("x"),before);
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.deepEqual(errors,[]);
  await page.close();
}

function inside(node, x, y) {
  const box = node.bounds || node;
  return x >= box.x-5 && x <= box.x+box.width+5 && y >= box.y-5 && y <= box.y+box.height+5;
}

async function inspectSvg(browser, folder, sample) {
  let svg, layout;
  if (folder === "baseline") {
    svg = await fs.readFile(path.join(artifacts, folder, sample + ".svg"));
    layout = JSON.parse(await fs.readFile(path.join(artifacts, folder, sample + ".layout.json"), "utf8"));
  } else {
    const source = await fs.readFile(path.join(artifacts, folder, sample + ".smd.json"), "utf8");
    const response = await fetch(base + "/api/generate", {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({source, format:"smd"}),
    });
    const result = await response.json();
    assert.equal(response.status, 200, JSON.stringify(result.diagnostics));
    svg = Buffer.from(result.svg);
    layout = result.layout;
  }
  const page = await browser.newPage({viewport:{width:1440,height:940}});
  await page.setContent('<body style="background:#fff;margin:16px"><img style="max-width:100%;max-height:900px" alt="UML" src="data:image/svg+xml;base64,' + svg.toString("base64") + '"></body>');
  await page.locator("img").evaluate(img => img.decode());
  await page.locator("img").screenshot({path:path.join(output,sample + "-" + folder + ".png")});
  if (sample !== "nested") {
    await page.close();
    return null;
  }
  const edge = layout.edges["transition-2"];
  const samples = [];
  for (let i = 1; i < edge.points.length; i++) {
    const a = edge.points[i-1], b = edge.points[i];
    for (let j = 2; j < 18; j++) {
      const x = a.x + j/20*(b.x-a.x), y = a.y + j/20*(b.y-a.y);
      if (!Object.entries(layout.nodes).some(([id,node]) => !["vertex-2","vertex-4"].includes(id) && inside(node,x,y)) &&
          !Object.values(layout.edges).some(item => item.labelBounds && inside(item.labelBounds,x,y))) samples.push([x,y]);
    }
  }
  assert(samples.length > 5, "Need line samples away from diagram text and leaves");
  const hits = await page.locator("img").evaluate((img, {samples, viewport}) => {
    const canvas = document.createElement("canvas");
    canvas.width = Math.ceil(viewport.width * 2);
    canvas.height = Math.ceil(viewport.height * 2);
    const context = canvas.getContext("2d");
    context.fillStyle = "white";
    context.fillRect(0,0,canvas.width,canvas.height);
    context.drawImage(img,0,0,canvas.width,canvas.height);
    const ratioX = canvas.width/viewport.width, ratioY = canvas.height/viewport.height;
    return samples.filter(([x,y]) => {
      const data = context.getImageData(Math.round((x-viewport.x)*ratioX)-1, Math.round((y-viewport.y)*ratioY)-1, 3, 3).data;
      for (let p = 0; p < data.length; p += 4) if (data[p] < 170 && data[p+1] < 170 && data[p+2] < 170) return true;
      return false;
    }).length / samples.length;
  }, {samples,viewport:layout.viewport});
  await page.close();
  return hits;
}

async function main() {
  await fs.mkdir(output,{recursive:true});
  const server = await start(["-m","pretty_smd","serve","--port",new URL(base).port],base+"/api/examples");
  let browser;
  try {
    browser = await chromium.launch({executablePath:process.env.CHROME || undefined, headless:true});
    await checkApp(browser);
    await checkAdvanced(browser);
    const before = await inspectSvg(browser,"baseline","nested");
    const after = await inspectSvg(browser,"after","nested");
    assert(before !== null && after !== null && after > 0.7 && after > before + 0.5,
      "Inner transition raster visibility: baseline=" + before + ", topology=" + after);
    await inspectSvg(browser,"after","orthogonal");
    await inspectSvg(browser,"after","synthetic-48");
    if (process.env.PRETTY_SMD_GALLERY) await checkGallery(browser,process.env.PRETTY_SMD_GALLERY);
    console.log("Browser and downloads passed. Nested arrow pixel coverage:", before, "→", after);
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
