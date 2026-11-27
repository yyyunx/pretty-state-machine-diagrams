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
};
const caseNames = {
  linear: "線性序列", resolvedBranch: "守衛分支", nested: "巢狀複合狀態",
  orthogonal: "正交區域", pseudostates: "偽狀態與邊界點",
};
const allowedSvg = new Set(["svg", "title", "desc", "defs", "marker", "path", "rect", "g",
  "line", "circle", "text", "tspan", "polyline"]);
let samples = {};
let current = null;
let view = {x: 0, y: 0, scale: 1, width: 1, height: 1};
let drag = null;
let busy = false;

function status(message) {
  el("status").textContent = message;
}

function formatControls() {
  const unavailable = el("format").value === "pa";
  const legacy = el("algorithm").value === "legacy";
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
  mount(result.svg);
  current = result;
  const viewport = result.layout.viewport;
  view.width = viewport.width;
  view.height = viewport.height;
  el("empty").hidden = true;
  el("download").disabled = false;
  el("item").textContent = "點選狀態或轉移查看資料。";
  el("time").textContent = "完整管線 " + result.quality.pipeline_ms + " ms";
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
  diagnostics(result.diagnostics);
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
      body: JSON.stringify({source, format: el("format").value, algorithm: el("algorithm").value, options})});
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
  const item = findInRegions(current.model.regions, edge || element.dataset.nodeId, edge ? "transitions" : "vertices");
  if (!item) return;
  const details = edge ? {
    Trigger: item.triggers || [], Guard: item.guard ?? null, Effect: item.effect ?? null,
    "互動原文": item.sourceText ?? null,
  } : {
    "名稱": item.displayName ?? "未命名", "種類": item.pseudostateKind || item.kind,
    "行為": item.behaviors || {},
  };
  el("item").textContent = JSON.stringify(details, null, 2);
  el("inspector").open = true;
}

el("generate").addEventListener("click", generate);
el("format").addEventListener("change", formatControls);
el("algorithm").addEventListener("change", formatControls);
el("example").addEventListener("change", () => {
  const sample = samples[el("example").value];
  if (!sample) return;
  el("source").value = JSON.stringify(sample, null, 2);
  el("format").value = "mock";
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
  if (current && event.button === 0) drag = {x:event.clientX, y:event.clientY, vx:view.x, vy:view.y, moved:false};
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
  if (!current) return;
  const kind = el("export").value;
  const svg = kind === "svg";
  const contents = svg ? current.svg : JSON.stringify(current[kind], null, 2) + "\n";
  const url = URL.createObjectURL(new Blob([contents], {type: svg ? "image/svg+xml" : "application/json"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = svg ? "diagram.svg" : "diagram." + kind + ".json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 500);
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
