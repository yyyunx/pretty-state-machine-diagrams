"use strict";

const el = id => document.getElementById(id);
const canvas = el("canvas");
const drawing = el("drawing");
const inBrowser = Boolean(window.prettySmdTransport);
const transport = window.prettySmdTransport || {
  async examples() {
    const response = await fetch("/api/examples");
    if (!response.ok) throw new Error("無法載入內建案例。");
    return response.json();
  },
  async request(action,payload) {
    const response = await fetch("/api/"+action,{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(payload)});
    return {ok:response.ok,status:response.status,body:await response.json()};
  },
};
const phases = {initializing:"初始化 Python Worker",runtime:"正在載入 Python 與 WebAssembly",
  packages:"正在載入 Python 套件與驗證依賴",imports:"正在初始化驗證及排版模組",
  package:"正在載入 Pretty SMD 套件",dependencies:"正在載入 Schema 驗證依賴",ready:"Python 引擎就緒",
  validate:"驗證模型",layout:"計算排版",render:"產生 SVG",quality:"計算品質",compare:"計算 Phase 3 對照",
  elk:"載入選配 ELK 並計算平面排版"};
const reportNames = {
  node_overlaps: "節點重疊", label_collisions: "標籤碰撞", edge_crossings: "連線交叉",
  edge_node_intersections: "連線穿過非端點節點", edge_overlap_length: "共線長度",
  disconnected_anchors: "斷開錨點", edge_bends: "轉折數", total_edge_length: "連線總長",
  diagram_area: "圖面面積", execution_ms: "排版時間（ms）", render_ms: "繪圖時間（ms）",
  pipeline_ms: "完整管線（ms）", semantic_preservation: "語意資料與 ID 完整",
  label_path_intersections: "標籤遮住轉移", broken_paths: "無效路徑",
};
const caseNames = {
  linear: "線性序列", resolvedBranch: "守衛分支", nested: "巢狀複合狀態",
  orthogonal: "正交區域", pseudostates: "偽狀態與邊界點",
  "benchmark-sparse": "Benchmark · 50 節點稀疏圖",
  "benchmark-cycles": "Benchmark · 25 節點循環",
  "benchmark-loops": "Benchmark · 25 節點自迴圈",
};
const allowedSvg = new Set(["svg", "title", "desc", "defs", "marker", "path", "rect", "g",
  "line", "circle", "text", "tspan", "polyline"]);
let samples = {};
let current = null;
let view = {x: 0, y: 0, scale: 1, width: 1, height: 1};
let drag = null;
let busy = false;
let displayed = null;
let focused = null;
let inputEpoch = 0;
const ns = "http://www.w3.org/2000/svg";

function status(message) {
  el("status").textContent = tr(message);
}

function formatControls() {
  const unavailable = el("format").value === "pa";
  const legacy = el("algorithm").value === "legacy";
  el("advanced-options").hidden = !["advanced","hybrid","elk"].includes(el("algorithm").value);
  el("elk-option").hidden = !inBrowser || el("algorithm").value!=="hybrid";
  el("pa-note").hidden = !unavailable;
  el("generate").disabled = busy || unavailable;
  el("validate").disabled = busy || unavailable;
  el("format-json").disabled = busy || unavailable;
  el("cancel").disabled = !busy;
  for (const button of document.querySelectorAll("[data-lesson]"))
    button.disabled = busy || !Object.hasOwn(samples,button.dataset.lesson);
  el("direction").disabled = legacy;
  for (const input of document.querySelectorAll("[data-option]")) input.disabled = legacy;
  editorControls();
}

function diagnostics(items) {
  const list = el("diagnostic-list");
  list.replaceChildren();
  for (const item of items) {
    const li = document.createElement("li");
    li.className = item.severity;
    li.textContent = [item.code, item.path, item.message].filter(Boolean).join(" · ");
    list.append(li);
  }
  if (items.length) el("diagnostics").open = true;
}

function updateView() {
  drawing.style.transform = "translate(" + view.x + "px," + view.y + "px) scale(" + view.scale + ")";
  const window = el("mini-window");
  if (window && displayed) {
    const bounds = displayed.layout.viewport;
    window.setAttribute("x",bounds.x-view.x/view.scale);
    window.setAttribute("y",bounds.y-view.y/view.scale);
    window.setAttribute("width",canvas.clientWidth/view.scale);
    window.setAttribute("height",canvas.clientHeight/view.scale);
  }
}

function fit() {
  if (!current) return;
  view.scale = Math.min(2, (canvas.clientWidth - 30) / view.width, (canvas.clientHeight - 30) / view.height);
  view.x = (canvas.clientWidth - view.scale * view.width) / 2;
  view.y = (canvas.clientHeight - view.scale * view.height) / 2;
  updateView();
}

function zoom(factor, x = canvas.clientWidth/2, y = canvas.clientHeight/2) {
  if (!current) return;
  const previous = view.scale;
  view.scale = Math.min(8, Math.max(.025, view.scale * factor));
  view.x = x - (x - view.x) * view.scale / previous;
  view.y = y - (y - view.y) * view.scale / previous;
  updateView();
}

function mount(svg) {
  const parsed = new DOMParser().parseFromString(svg, "image/svg+xml");
  if (parsed.doctype || parsed.documentElement.localName !== "svg" ||
      Array.from(parsed.querySelectorAll("*")).some(item =>
        item.namespaceURI!==ns || !allowedSvg.has(item.localName) ||
        Array.from(item.attributes).some(attr => /^on/i.test(attr.name) || /href$|^style$/i.test(attr.name)
          || (/^(fill|stroke|marker-|filter|mask)/i.test(attr.name) && /url\s*\(/i.test(attr.value)
            && attr.value!=="url(#arrow)")))) {
    throw new Error("收到無法顯示的 SVG。");
  }
  drawing.replaceChildren(document.importNode(parsed.documentElement, true));
}

function show(result) {
  current = result;
  focused = null;
  selectedStates = new Set();
  el("comparison").hidden = !result.baseline;
  if (result.baseline) {
    const b = result.baseline.quality, a = result.quality;
    el("after").textContent = a.optimization?.mode==="elk" ? "ELK" : tr("本次結果");
    el("delta").textContent = tr("連線交叉") + " " + b.edge_crossings + " → " + a.edge_crossings
      + "　" + tr("轉折數") + " " + b.edge_bends + " → " + a.edge_bends
      + "　" + tr("排版時間（ms）") + " " + b.execution_ms + " → " + a.execution_ms;
  }
  tree();
  diagnostics(result.diagnostics);
  showVersion(false);
}

function showVersion(before) {
  const result = before ? current.baseline : (projection || current);
  if (!result) return;
  mount(result.svg);
  displayed = result;
  el("before").setAttribute("aria-pressed",String(before));
  el("after").setAttribute("aria-pressed",String(!before));
  const viewport = result.layout.viewport;
  view.width = viewport.width;
  view.height = viewport.height;
  el("empty").hidden = true;
  el("download").disabled = false;
  if (!focused) el("item").textContent = tr("點選狀態或轉移查看資料。");
  const optimization = result.quality.optimization;
  if (optimization?.reasons) {
    el("selection").hidden = false;
    const names = {"high-edge-density":"密集轉移","large-scc":"大型 SCC",
      "composite-hierarchy":"複合階層","cross-level-transitions":"跨階層轉移",
      "bounded-runtime":"有時間或規模限制","optional-external-engine-unavailable":"使用內建候選",
      "small-sparse-graph":"小型稀疏圖","advanced-candidates-rejected":"進階候選無解，已回退",
      "flat-elk-layout":"ELK 平面圖排版"};
    el("selection").textContent = optimization.selected + " · " +
      optimization.reasons.map(reason=>names[reason]||reason).join("、");
  } else el("selection").hidden = true;
  const candidates = el("candidate-list");
  candidates.replaceChildren();
  candidates.hidden = !optimization?.candidates.length;
  for (const candidate of optimization?.candidates || []) {
    const row = document.createElement("li");
    row.textContent = [candidate.candidate, candidate.status,
      candidate.crossings===undefined ? null : tr("連線交叉")+" "+candidate.crossings,
      candidate.score===undefined ? null : tr("分數")+" "+candidate.score.toFixed(2),
      candidate.elapsed_ms===undefined ? null : candidate.elapsed_ms+" ms", candidate.detail].filter(Boolean).join(" · ");
    candidates.append(row);
  }
  const runtime = result.runtime ? " · " + tr("瀏覽器 Python") + " " + Math.round(result.runtime.engineMs) + " ms" : "";
  el("time").textContent = (result.quality.pipeline_ms===undefined ? "" : tr("完整管線") + " " +
    result.quality.pipeline_ms + " ms") + (optimization
    ? " · " + optimization.mode + " · " + optimization.candidates.length + " " + tr("個候選") : "") + runtime;
  const list = el("quality-list");
  list.replaceChildren();
  for (const [key, label] of Object.entries(reportNames)) {
    const term = document.createElement("dt");
    term.textContent = tr(label);
    const value = document.createElement("dd");
    value.textContent = typeof result.quality[key] === "boolean" ?
      tr(result.quality[key] ? "通過" : "失敗") : String(result.quality[key] ?? "—");
    list.append(term, value);
  }
  minimap();
  highlight();
  fit();
  editorControls();
}

async function generate(action="generate", {clearEdits=false}={}) {
  if (typeof action!=="string") action = "generate";
  const source = el("source").value.trim();
  if (!source || busy || el("format").value === "pa") {
    if (!source) status("請先輸入 JSON。");
    return;
  }
  const options = {direction: el("direction").value};
  for (const field of document.querySelectorAll("[data-option]")) {
    if (!field.disabled && !field.checkValidity()) {
      field.reportValidity();
      return;
    }
    if (!field.disabled && field.value !== "") options[field.dataset.option] = field.valueAsNumber;
  }
  busy = true;
  formatControls();
  const epoch = inputEpoch;
  const algorithm = el("algorithm").value, mode = el("mode").value;
  const flags = {allowRotate:el("rotate").checked,compare:el("compare").checked,useElk:el("use-elk").checked};
  status(action==="generate" ? "正在驗證及生成圖形…" : "正在處理輸入…");
  try {
    const response = await transport.request(action,{source,format:el("format").value,algorithm,options,mode,...flags});
    if (epoch!==inputEpoch) return;
    const result = response.body;
    if (!response.ok) {
      diagnostics(result.diagnostics || []);
      status(response.status===499 ? "已取消運算。" : current ?
        "這次操作失敗。預覽保留上一份圖形。" : "操作失敗，請查看診斷。");
      return;
    }
    if (action==="format") {
      el("source").value = result.formatted;
      diagnostics([]);
      status("JSON 已格式化。");
    } else if (action==="validate") {
      diagnostics(result.diagnostics);
      status("Semantic Model 驗證完成。");
    } else {
      if (!await acceptGeneration(result,{options,algorithm,mode,flags},epoch,!clearEdits)) return;
      status("狀態機圖已生成。");
    }
  } catch (error) {
    status(String(error.message || error));
  } finally {
    busy = false;
    formatControls();
  }
}

function findInRegions(regions, id, field) {
  for (const region of regions) {
    const direct = region[field].find(item => item.id === id);
    if (direct) return direct;
    for (const vertex of region.vertices) {
      const nested = findInRegions(vertex.regions || [], id, field);
      if (nested) return nested;
    }
  }
  return null;
}

function inspect(target, extend=false) {
  if (!current) return;
  const element = target.closest("[data-node-id], [data-node-label-id], [data-edge-id]");
  if (!element) return;
  const edge = element.dataset.edgeId;
  selectItem(edge || element.dataset.nodeId || element.dataset.nodeLabelId, edge ? "transitions" : "vertices",extend);
}

function selectItem(id, field, extend=false) {
  const edge = field === "transitions";
  const item = findInRegions(current.model.regions,id,field);
  if (!item) return;
  if (!extend || edge) selectedStates = new Set();
  if (!edge) selectedStates.add(id);
  focused = {id,edge,item};
  const details = edge ? {
    Trigger: item.triggers || [], Guard: item.guard ?? null, Effect: item.effect ?? null,
    [tr("互動原文")]: item.sourceText ?? null,
  } : {
    [tr("名稱")]: item.displayName ?? tr("未命名"), [tr("種類")]: item.pseudostateKind || item.kind,
    [tr("行為")]: item.behaviors || {},
  };
  el("item").textContent = JSON.stringify(details, null, 2);
  el("inspector").open = true;
  highlight();
  editorControls();
}

function highlight() {
  for (const node of drawing.querySelectorAll("[data-node-id]")) {
    node.classList.toggle("selected-node",selectedStates.has(node.dataset.nodeId));
  }
  for (const edge of drawing.querySelectorAll("[data-edge-id]")) {
    const id = edge.dataset.edgeId;
    const transition = focused && !focused.edge
      ? findInRegions(current.model.regions,id,"transitions") : null;
    const related = focused && (focused.edge ? id===focused.id
      : transition && (transition.sourceId===focused.id || transition.targetId===focused.id));
    edge.classList.toggle("related-edge",!!related);
  }
}

function tree() {
  const root = el("tree");
  root.replaceChildren();
  if (!current) return;
  const query = el("search").value.toLocaleLowerCase().trim();
  function button(text,id,field) {
    const item = document.createElement("li");
    const control = document.createElement("button");
    control.type = "button";
    control.textContent = text;
    control.addEventListener("click",() => selectItem(id,field));
    item.append(control);
    return item;
  }
  for (const region of current.model.regions) walk(region,root);
  if (!root.children.length) {
    const empty = document.createElement("li");
    empty.textContent = "沒有相符的狀態或轉移。";
    root.append(empty);
  }
  function walk(region,list) {
    const branch = document.createElement("ul");
    for (const node of region.vertices) {
      const text = node.displayName || ("未命名 · " + (node.pseudostateKind || node.kind));
      const children = document.createElement("ul");
      for (const nested of node.regions || []) walk(nested,children);
      if (!query || text.toLocaleLowerCase().includes(query) || children.children.length) {
        const item = button(text,node.id,"vertices");
        if (children.children.length) item.append(children);
        branch.append(item);
      }
    }
    if (query) {
      for (const edge of region.transitions) {
        const fields = [...(edge.triggers||[]),edge.guard,edge.effect,edge.sourceText].filter(Boolean);
        if (fields.join(" ").toLocaleLowerCase().includes(query)) {
          branch.append(button(edge.sourceText ?? fields.join(" "),edge.id,"transitions"));
        }
      }
    }
    if (!branch.children.length) return;
    const item = document.createElement("li");
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = region.displayName || "未命名區域";
    details.open = true;
    details.append(summary,branch);
    item.append(details);
    list.append(item);
  }
}

function minimap() {
  const map = el("mini-svg");
  map.replaceChildren();
  const geometry = displayed.layout;
  el("minimap").hidden = Object.keys(geometry.nodes).length < 18;
  if (el("minimap").hidden) return;
  const v = geometry.viewport;
  map.setAttribute("viewBox",[v.x,v.y,v.width,v.height].join(" "));
  const box = (b,css) => {
    const r = document.createElementNS(ns,"rect");
    for (const key of ["x","y","width","height"]) r.setAttribute(key,b[key]);
    r.setAttribute("class",css);
    map.append(r);
    return r;
  };
  for (const part of Object.values(geometry.nodes)) box(part.bounds,"mini-node");
  box(v,"mini-window").id = "mini-window";
}

el("generate").addEventListener("click", generate);
el("validate").addEventListener("click",()=>generate("validate"));
el("format-json").addEventListener("click",()=>generate("format"));
el("cancel").hidden = !inBrowser;
el("cancel").addEventListener("click",()=>transport.cancel?.());
function invalidateInput() {
  inputEpoch++;
  if (busy && transport.cancel) {
    transport.cancel();
    status("輸入已變更，請重新生成。");
  }
}
el("source").addEventListener("input",invalidateInput);
document.querySelector(".editor").addEventListener("change",event => {
  if (event.target.matches("#example,#format,#file,#algorithm,#mode,#rotate,#direction,#compare,#use-elk,[data-option]")) invalidateInput();
});
if (inBrowser) {
  el("algorithm").add(new Option("ELK 平面圖","elk"));
  const runtime = el("runtime-note");
  runtime.hidden = false;
  let text = "Python 引擎會在第一次操作時載入。";
  const update = () => {runtime.textContent = tr(navigator.onLine ? "線上" : "離線") + " · " + tr(text);};
  transport.listen(phase => { text = phases[phase] || phase; update(); });
  window.addEventListener("online",update);
  window.addEventListener("offline",update);
  document.addEventListener("DOMContentLoaded",update);
  el("language").addEventListener("change",()=>queueMicrotask(update));
}
el("format").addEventListener("change", formatControls);
el("algorithm").addEventListener("change", formatControls);
el("before").addEventListener("click",() => showVersion(true));
el("after").addEventListener("click",() => showVersion(false));
el("search").addEventListener("input",tree);
el("mini-fit").addEventListener("click",fit);
function saveFile(contents,type,name) {
  const url = URL.createObjectURL(new Blob([contents],{type}));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url),500);
}
el("save-settings").addEventListener("click",() => {
  const settings = {version:1,algorithm:el("algorithm").value,mode:el("mode").value,
    direction:el("direction").value,allowRotate:el("rotate").checked,options:{}};
  for (const field of document.querySelectorAll("[data-option]")) {
    if (field.value!=="" && !field.checkValidity()) {
      field.reportValidity();
      return;
    }
    if (field.value!=="") settings.options[field.dataset.option] = field.valueAsNumber;
  }
  saveFile(JSON.stringify(settings,null,2)+"\n","application/json","pretty-smd.settings.json");
});
el("load-settings").addEventListener("change",async event => {
  try {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size>16384) throw new Error("設定檔超過 16 KiB。");
    const settings = JSON.parse(await file.text());
    if (settings?.version!==1 || !["topology","legacy","advanced","hybrid","elk"].includes(settings.algorithm) ||
        !["fast","balanced","quality"].includes(settings.mode) ||
        !["horizontal","vertical"].includes(settings.direction) ||
        typeof settings.allowRotate!=="boolean" || !settings.options ||
        typeof settings.options!=="object" || Array.isArray(settings.options)) throw new Error("設定格式無效。");
    const fields = new Map(Array.from(document.querySelectorAll("[data-option]"), field => [field.dataset.option,field]));
    for (const [key,val] of Object.entries(settings.options)) {
      const field = fields.get(key);
      if (!field || typeof val!=="number" || !Number.isFinite(val) || val<Number(field.min) || val>Number(field.max)) {
        throw new Error("排版參數無效。");
      }
    }
    for (const [key,field] of fields) field.value = settings.options[key] ?? "";
    el("algorithm").value = settings.algorithm;
    el("mode").value = settings.mode;
    el("direction").value = settings.direction;
    el("rotate").checked = settings.allowRotate;
    formatControls();
    status("已載入排版設定。按生成可更新預覽。");
  } catch (error) {
    status(error.message);
  } finally {
    event.target.value = "";
  }
});
el("mini-svg").addEventListener("click",event => {
  const map = el("mini-svg");
  const matrix = map.getScreenCTM();
  if (!matrix || !displayed) return;
  const point = new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());
  const bounds = displayed.layout.viewport;
  view.x = canvas.clientWidth/2-(point.x-bounds.x)*view.scale;
  view.y = canvas.clientHeight/2-(point.y-bounds.y)*view.scale;
  updateView();
});
el("example").addEventListener("change", () => {
  const sample = samples[el("example").value];
  if (!sample) return;
  el("source").value = JSON.stringify(sample, null, 2);
  el("format").value = sample.schemaVersion ? "smd" : "mock";
  formatControls();
});
for (const button of document.querySelectorAll("[data-lesson]")) {
  button.addEventListener("click",()=>{
    el("example").value = button.dataset.lesson;
    el("example").dispatchEvent(new Event("change",{bubbles:true}));
    generate();
  });
}
el("file").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 512 * 1024) {
    status("檔案超過 512 KiB。");
    return;
  }
  try {
    el("source").value = await file.text();
    el("format").value = "auto";
    formatControls();
    status("檔案已載入。");
  } catch {
    status("無法讀取檔案。");
  }
});
el("theme").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme !== "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  el("theme").setAttribute("aria-pressed", String(dark));
  el("theme").textContent = tr(dark ? "淺色模式" : "深色模式");
});
el("fit").addEventListener("click", fit);
el("reset").addEventListener("click", () => {
  view.x = 16; view.y = 16; view.scale = 1; updateView();
});
el("zoom-in").addEventListener("click", () => zoom(1.25));
el("zoom-out").addEventListener("click", () => zoom(.8));
el("fullscreen").addEventListener("click", async () => {
  if (document.fullscreenElement) await document.exitFullscreen();
  else if (el("viewer").requestFullscreen) await el("viewer").requestFullscreen();
});
document.addEventListener("fullscreenchange", fit);
canvas.addEventListener("wheel", event => {
  if (!current) return;
  event.preventDefault();
  const rect = canvas.getBoundingClientRect();
  zoom(event.deltaY < 0 ? 1.13 : .89, event.clientX-rect.left, event.clientY-rect.top);
}, {passive: false});
canvas.addEventListener("pointerdown", event => {
  if (!current || event.button!==0 || event.target.closest("#minimap")) return;
  const node = event.target.closest("[data-node-id], [data-node-label-id]");
  const id = !el("edit-mode").disabled && el("edit-mode").checked && (node?.dataset.nodeId || node?.dataset.nodeLabelId);
  drag = {x:event.clientX,y:event.clientY,vx:view.x,vy:view.y,moved:false,id,scale:view.scale};
  if (id) {
    drag.bounds = current.layout.nodes[id].bounds;
    drag.locked = Object.hasOwn(locked,id);
  }
});
canvas.addEventListener("pointermove", event => {
  if (!drag) return;
  const dx = event.clientX-drag.x, dy = event.clientY-drag.y;
  if (!drag.moved && Math.hypot(dx,dy) < 4) return;
  if (!drag.moved) {
    canvas.setPointerCapture(event.pointerId);
    if (drag.id && !drag.locked) {
      drag.ghost = document.createElementNS(ns,"rect");
      drag.ghost.classList.add("node-ghost");
      drag.ghost.setAttribute("width",drag.bounds.width);
      drag.ghost.setAttribute("height",drag.bounds.height);
      drawing.querySelector("svg").append(drag.ghost);
    }
  }
  drag.moved = true;
  canvas.classList.add("dragging");
  if (drag.id) {
    drag.next = {x:drag.bounds.x+dx/drag.scale,y:drag.bounds.y+dy/drag.scale};
    drag.ghost?.setAttribute("x",drag.next.x);
    drag.ghost?.setAttribute("y",drag.next.y);
  } else {
    view.x = drag.vx + dx; view.y = drag.vy + dy; updateView();
  }
});
canvas.addEventListener("pointerup", event => {
  if (drag?.id && drag.next && drag.locked) el("edit-status").textContent = tr("此節點已鎖定。");
  if (drag?.id && drag.next && !drag.locked) {
    selectItem(drag.id,"vertices");
    changeScene("edit",{moves:{[drag.id]:drag.next},locked});
  }
  if (drag && !drag.moved) inspect(event.target,event.shiftKey);
  drag?.ghost?.remove();
  drag = null; canvas.classList.remove("dragging");
});
canvas.addEventListener("pointercancel", () => {
  drag?.ghost?.remove(); drag = null; canvas.classList.remove("dragging");
});
canvas.addEventListener("keydown", event => {
  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); inspect(event.target,event.shiftKey); }
});
async function pngFrom(result) {
  const {width,height} = result.layout.viewport;
  const scale = Math.min(2,4096/width,4096/height,Math.sqrt(12_000_000/(width*height)));
  const image = new Image();
  const url = URL.createObjectURL(new Blob([result.svg],{type:"image/svg+xml"}));
  try {
    image.src = url;
    await image.decode();
    const output = document.createElement("canvas");
    output.width = Math.max(1,Math.ceil(width*scale));
    output.height = Math.max(1,Math.ceil(height*scale));
    output.getContext("2d").drawImage(image,0,0,output.width,output.height);
    const blob = await new Promise(resolve => output.toBlob(resolve,"image/png"));
    if (!blob) throw new Error("無法匯出 PNG。");
    return blob;
  } finally {
    URL.revokeObjectURL(url);
  }
}
el("download").addEventListener("click", async () => {
  if (!displayed) return;
  const kind = el("export").value;
  if (kind==="png") {
    try { saveFile(await pngFrom(displayed),"image/png","diagram.png"); }
    catch (error) { status(error.message); }
    return;
  }
  const svg = kind === "svg" || kind === "svg-original";
  const scene = kind==="svg-original" || (projection && displayed===projection && kind==="layout") ? current : displayed;
  const contents = svg ? scene.svg : JSON.stringify(kind==="model" ? current.model : scene[kind],null,2) + "\n";
  saveFile(contents,svg ? "image/svg+xml" : "application/json",svg ? "diagram.svg" : "diagram." + kind + ".json");
});

document.addEventListener("DOMContentLoaded",()=>transport.examples().then(data => {
  samples = data;
  for (const [key,label] of Object.entries(caseNames)) {
    const option = new Option(tr(label),key);
    option.dataset.translate = label;
    el("example").add(option);
  }
  const requested = new URLSearchParams(location.search).get("case");
  const sample = requested && Object.hasOwn(samples,requested) ? requested : "orthogonal";
  if (!Object.hasOwn(caseNames,sample)) el("example").add(new Option(samples[sample].displayName || sample,sample));
  el("example").value = sample;
  el("example").dispatchEvent(new Event("change"));
  if (!inBrowser) return generate();
}).catch(error => status(error.message)));
