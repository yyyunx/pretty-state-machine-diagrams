"use strict";

const el = id => document.getElementById(id);
const canvas = el("canvas");
const drawing = el("drawing");
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
const ns = "http://www.w3.org/2000/svg";

function status(message) {
  el("status").textContent = message;
}

function formatControls() {
  const unavailable = el("format").value === "pa";
  const legacy = el("algorithm").value === "legacy";
  el("advanced-options").hidden = el("algorithm").value !== "advanced";
  el("pa-note").hidden = !unavailable;
  el("generate").disabled = busy || unavailable;
  el("direction").disabled = legacy;
  for (const input of document.querySelectorAll("[data-option]")) input.disabled = legacy;
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
  if (parsed.documentElement.localName !== "svg" ||
      Array.from(parsed.querySelectorAll("*")).some(item =>
        !allowedSvg.has(item.localName) ||
        Array.from(item.attributes).some(attr => /^on/i.test(attr.name) || /href$/i.test(attr.name)))) {
    throw new Error("收到無法顯示的 SVG。");
  }
  drawing.replaceChildren(document.importNode(parsed.documentElement, true));
}

function show(result) {
  current = result;
  focused = null;
  el("comparison").hidden = !result.baseline;
  if (result.baseline) {
    const b = result.baseline.quality, a = result.quality;
    el("delta").textContent = "交叉 " + b.edge_crossings + " → " + a.edge_crossings
      + "　轉折 " + b.edge_bends + " → " + a.edge_bends
      + "　排版時間 " + b.execution_ms + " → " + a.execution_ms + " ms";
  }
  tree();
  diagnostics(result.diagnostics);
  showVersion(false);
}

function showVersion(before) {
  const result = before ? current.baseline : current;
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
  if (!focused) el("item").textContent = "點選狀態或轉移查看資料。";
  const optimization = result.quality.optimization;
  el("time").textContent = "完整管線 " + result.quality.pipeline_ms + " ms" + (optimization
    ? " · " + optimization.mode + " · " + optimization.candidates.length + " 個候選" : "");
  const list = el("quality-list");
  list.replaceChildren();
  for (const [key, label] of Object.entries(reportNames)) {
    const term = document.createElement("dt");
    term.textContent = label;
    const value = document.createElement("dd");
    value.textContent = typeof result.quality[key] === "boolean" ?
      (result.quality[key] ? "通過" : "失敗") : String(result.quality[key] ?? "—");
    list.append(term, value);
  }
  minimap();
  highlight();
  fit();
}

async function generate() {
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
  status("正在驗證及生成圖形…");
  try {
    const response = await fetch("/api/generate", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({source, format: el("format").value, algorithm: el("algorithm").value, options,
        mode:el("mode").value, allowRotate:el("rotate").checked, compare:el("compare").checked})});
    const result = await response.json();
    if (!response.ok) {
      diagnostics(result.diagnostics || []);
      status(current ? "這次生成失敗。預覽保留上一份圖形。" : "生成失敗，請查看診斷。");
      return;
    }
    show(result);
    status("狀態機圖已生成。");
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

function inspect(target) {
  if (!current) return;
  const element = target.closest("[data-node-id], [data-edge-id]");
  if (!element) return;
  const edge = element.dataset.edgeId;
  selectItem(edge || element.dataset.nodeId, edge ? "transitions" : "vertices");
}

function selectItem(id, field) {
  const edge = field === "transitions";
  const item = findInRegions(current.model.regions,id,field);
  if (!item) return;
  focused = {id,edge,item};
  const details = edge ? {
    Trigger: item.triggers || [], Guard: item.guard ?? null, Effect: item.effect ?? null,
    "互動原文": item.sourceText ?? null,
  } : {
    "名稱": item.displayName ?? "未命名", "種類": item.pseudostateKind || item.kind,
    "行為": item.behaviors || {},
  };
  el("item").textContent = JSON.stringify(details, null, 2);
  el("inspector").open = true;
  highlight();
}

function highlight() {
  for (const node of drawing.querySelectorAll("[data-node-id]")) {
    node.classList.toggle("selected-node", !!(focused && !focused.edge && node.dataset.nodeId === focused.id));
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
    if (settings?.version!==1 || !["topology","legacy","advanced"].includes(settings.algorithm) ||
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
  el("theme").textContent = dark ? "淺色模式" : "深色模式";
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
  if (current && event.button === 0 && !event.target.closest("#minimap"))
    drag = {x:event.clientX, y:event.clientY, vx:view.x, vy:view.y, moved:false};
});
canvas.addEventListener("pointermove", event => {
  if (!drag) return;
  const dx = event.clientX-drag.x, dy = event.clientY-drag.y;
  if (!drag.moved && Math.hypot(dx,dy) < 4) return;
  if (!drag.moved) canvas.setPointerCapture(event.pointerId);
  drag.moved = true;
  canvas.classList.add("dragging");
  view.x = drag.vx + dx; view.y = drag.vy + dy; updateView();
});
canvas.addEventListener("pointerup", event => {
  if (drag && !drag.moved) inspect(event.target);
  drag = null; canvas.classList.remove("dragging");
});
canvas.addEventListener("pointercancel", () => { drag = null; canvas.classList.remove("dragging"); });
canvas.addEventListener("keydown", event => {
  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); inspect(event.target); }
});
el("download").addEventListener("click", () => {
  if (!displayed) return;
  const kind = el("export").value;
  const svg = kind === "svg";
  const contents = svg ? displayed.svg : JSON.stringify(kind==="model" ? current.model : displayed[kind],null,2) + "\n";
  saveFile(contents,svg ? "image/svg+xml" : "application/json",svg ? "diagram.svg" : "diagram." + kind + ".json");
});

fetch("/api/examples").then(response => {
  if (!response.ok) throw new Error("無法載入內建案例。");
  return response.json();
}).then(data => {
  samples = data;
  for (const [key,label] of Object.entries(caseNames)) el("example").add(new Option(label,key));
  el("example").value = "orthogonal";
  el("example").dispatchEvent(new Event("change"));
  return generate();
}).catch(error => status(error.message));
