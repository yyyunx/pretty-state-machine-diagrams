"use strict";

const projectKey = "pretty-smd.workspace.v1";
let locked = {};
let collapsed = [];
let projection = null;
let automatic = null;
let layoutSettings = null;
let selectedStates = new Set();
const history = [];
const redoHistory = [];

function editorControls() {
  const editable = current && displayed!==current.baseline && !busy;
  const state = editable && focused && !focused.edge && displayed.layout.nodes[focused.id];
  const selection = state ? [...selectedStates].filter(key=>Object.hasOwn(displayed.layout.nodes,key)) : [];
  el("edit-mode").disabled = !editable || Boolean(projection);
  el("toggle-lock").disabled = !state || Boolean(projection);
  const isLocked = selection.length>0 && selection.every(key=>Object.hasOwn(locked,key));
  el("toggle-lock").setAttribute("aria-pressed",String(isLocked));
  el("toggle-lock").textContent = tr(isLocked ? "解除鎖定" : "鎖定節點") + (selection.length>1 ? " ("+selection.length+")" : "");
  el("toggle-collapse").disabled = !state || focused.item.kind!=="composite";
  const isCollapsed = Boolean(state && collapsed.includes(focused.id));
  el("toggle-collapse").setAttribute("aria-pressed",String(isCollapsed));
  el("toggle-collapse").textContent = tr(isCollapsed ? "展開複合狀態" : "收合複合狀態");
  el("undo").disabled = busy || !history.length;
  el("redo").disabled = busy || !redoHistory.length;
  el("reset-layout").disabled = busy || !current ||
    (current===automatic && !Object.keys(locked).length && !collapsed.length);
  el("workspace-save").disabled = !current || busy;
  el("workspace-file").disabled = busy;
  el("workspace-restore").disabled = busy || !storedWorkspace();
  for (const node of drawing.querySelectorAll("[data-node-id]"))
    node.classList.toggle("locked-node",Object.hasOwn(locked,node.dataset.nodeId));
}

function snapshot() {
  return {current,locked,collapsed,projection,automatic,layoutSettings,focused,selectedStates:new Set(selectedStates)};
}

function remember() {
  if (!current) return;
  history.push(snapshot());
  if (history.length>15) history.shift();
  redoHistory.length = 0;
}

function renderEditor(focus=focused, keepView=false) {
  const previous = {...view};
  const viewport = displayed?.layout.viewport;
  const selection = [...selectedStates];
  show(current);
  if (focus && Object.hasOwn(focus.edge?displayed.layout.edges:displayed.layout.nodes,focus.id))
    selectItem(focus.id,focus.edge?"transitions":"vertices");
  if (focus && !focus.edge && focused) {
    for (const key of selection) if (Object.hasOwn(displayed.layout.nodes,key)) selectedStates.add(key);
    highlight();
  }
  if (keepView && viewport) {
    view = {...view,...previous,width:view.width,height:view.height};
    view.x += (displayed.layout.viewport.x-viewport.x)*view.scale;
    view.y += (displayed.layout.viewport.y-viewport.y)*view.scale;
    updateView();
  }
  editorControls();
  saveLocal();
}

function restoreHistory(from,to) {
  if (busy || !from.length) return;
  to.push(snapshot());
  const previous = current.model;
  ({current,locked,collapsed,projection,automatic,layoutSettings,focused,selectedStates} = from.pop());
  syncSettings(layoutSettings);
  if (!sameDocument(previous,current.model)) syncSource(current.model);
  renderEditor();
  formatControls();
}

function sameDocument(a,b) {
  return a===b || (a && b && typeof a==="object" && typeof b==="object" &&
    Array.isArray(a)===Array.isArray(b) && Object.keys(a).length===Object.keys(b).length &&
    Object.keys(a).every(key=>Object.hasOwn(b,key) && sameDocument(a[key],b[key])));
}

async function editRequest(action,result,details,options=layoutSettings.options) {
  const response = await transport.request(action,{source:JSON.stringify(result.model),layout:result.layout,options,...details});
  if (!response.ok) {
    diagnostics(response.body.diagnostics || []);
    throw new Error(response.body.diagnostics?.[0]?.message || tr("未套用變更。"));
  }
  return response.body;
}

async function acceptGeneration(result,settings,epoch,preserveEdits) {
  const same = preserveEdits && current && sameDocument(result.model,current.model);
  const retainedLocks = same ? locked : {};
  const retainedFold = same ? collapsed : [];
  const adjusted = Object.keys(retainedLocks).length
    ? await editRequest("edit",result,{moves:retainedLocks,locked:{}},settings.options) : result;
  const nextProjection = retainedFold.length
    ? await editRequest("collapse",adjusted,{collapsed:retainedFold},settings.options) : null;
  if (epoch!==inputEpoch) return false;
  if (adjusted!==result && result.baseline) adjusted.baseline = result.baseline;
  remember();
  current = adjusted;
  automatic = result;
  locked = retainedLocks;
  collapsed = retainedFold;
  projection = nextProjection;
  layoutSettings = settings;
  renderEditor(null);
  return true;
}

async function changeScene(action,details) {
  if (busy || !current) return;
  busy = true;
  formatControls();
  try {
    const result = await editRequest(action,current,details);
    remember();
    if (action==="edit") {
      if (current.baseline) result.baseline = current.baseline;
      current = result;
    } else {
      collapsed = details.collapsed;
      projection = collapsed.length ? result : null;
    }
    renderEditor(focused,action==="edit");
    const counts = result.edit;
    const folded = Object.values(result.summary || {}).reduce(([vertices,edges],item)=>
      [vertices+item.vertices,edges+item.internal_transitions],[0,0]);
    el("edit-status").textContent = counts
      ? tr("重新路由") + ": " + counts.rerouted + " · " + tr("其他節點位移") + ": " + counts.unaffected_displacement
      : tr("已隱藏的內部節點") + ": " + folded[0] + " · " + tr("內部轉移") + ": " + folded[1];
  } catch (error) {
    el("edit-status").textContent = error.message;
  } finally {
    busy = false;
    formatControls();
  }
}

function workspaceDocument() {
  return current && {version:1,model:current.model,layout:current.layout,...layoutSettings,locked,collapsed};
}

function storedWorkspace() {
  try { return localStorage.getItem(projectKey); }
  catch { return null; }
}

function saveLocal() {
  if (!current || !el("auto-save").checked) return;
  try { localStorage.setItem(projectKey,JSON.stringify(workspaceDocument())); }
  catch { el("edit-status").textContent = tr("裝置無法保存此工作區，請下載檔案。"); }
}

function syncSettings(settings) {
  el("algorithm").value = settings.algorithm==="elk" && !inBrowser ? "hybrid" : settings.algorithm;
  el("mode").value = settings.mode;
  el("direction").value = settings.options.direction || "horizontal";
  el("rotate").checked = settings.flags.allowRotate;
  el("compare").checked = settings.flags.compare;
  el("use-elk").checked = settings.flags.useElk;
  for (const field of document.querySelectorAll("[data-option]")) {
    const setting = field.dataset.option;
    field.value = Object.hasOwn(settings.options,setting) ? settings.options[setting] : field.defaultValue;
  }
}

function syncSource(model) {
  el("source").value = JSON.stringify(model,null,2);
  el("format").value = "smd";
  el("example").value = "";
  inputEpoch++;
}

async function restoreWorkspace(source) {
  if (!source || busy) return;
  busy = true;
  formatControls();
  try {
    const response = await transport.request("workspace",{source});
    if (!response.ok) {
      diagnostics(response.body.diagnostics || []);
      throw new Error(response.body.diagnostics?.[0]?.message || tr("無法開啟工作區。"));
    }
    const {workspace,projection:nextProjection,...result} = response.body;
    remember();
    current = result;
    ({locked,collapsed} = workspace);
    projection = nextProjection;
    automatic = null;
    layoutSettings = {algorithm:workspace.algorithm,mode:workspace.mode,options:workspace.options,flags:workspace.flags};
    syncSettings(layoutSettings);
    syncSource(result.model);
    renderEditor(null);
    el("edit-status").textContent = tr("工作區已載入。");
  } catch (error) {
    el("edit-status").textContent = error.message;
  } finally {
    busy = false;
    formatControls();
  }
}

el("undo").addEventListener("click",()=>restoreHistory(history,redoHistory));
el("redo").addEventListener("click",()=>restoreHistory(redoHistory,history));
el("toggle-lock").addEventListener("click",()=>{
  if (el("toggle-lock").disabled) return;
  remember();
  const ids = [...selectedStates].filter(key=>Object.hasOwn(current.layout.nodes,key));
  const unlock = ids.every(id=>Object.hasOwn(locked,id));
  locked = {...locked};
  for (const id of ids) {
    if (unlock) delete locked[id];
    else {
      const {x,y} = current.layout.nodes[id].bounds;
      Object.defineProperty(locked,id,{value:{x,y},enumerable:true,configurable:true});
    }
  }
  saveLocal(); editorControls();
});
el("toggle-collapse").addEventListener("click",()=>{
  if (el("toggle-collapse").disabled) return;
  const {id} = focused;
  changeScene("collapse",{collapsed:collapsed.includes(id) ? collapsed.filter(key=>key!==id) : [...collapsed,id]});
});
el("reset-layout").addEventListener("click",()=>{
  if (el("reset-layout").disabled) return;
  if (!automatic) {
    syncSettings(layoutSettings);
    syncSource(current.model);
    formatControls();
    generate("generate",{clearEdits:true});
    return;
  }
  remember();
  current = automatic;
  locked = {}; collapsed = []; projection = null;
  renderEditor();
});
el("workspace-save").addEventListener("click",()=>saveFile(JSON.stringify(workspaceDocument(),null,2)+"\n",
  "application/json","diagram.workspace.json"));
el("workspace-file").addEventListener("change",async event=>{
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size>1024*1024) throw new Error(tr("工作區檔案超過 1 MiB。"));
    await restoreWorkspace(await file.text());
  } catch (error) { el("edit-status").textContent = error.message; }
  finally { event.target.value = ""; }
});
el("workspace-restore").addEventListener("click",()=>restoreWorkspace(storedWorkspace()));
el("workspace-clear").addEventListener("click",()=>{
  try { localStorage.removeItem(projectKey); }
  catch { return; }
  el("auto-save").checked = false;
  editorControls();
});
el("auto-save").addEventListener("change",()=>{ saveLocal(); editorControls(); });
document.addEventListener("keydown",event=>{
  if (!(event.ctrlKey || event.metaKey) || event.altKey || event.target.closest("input,textarea,select,[contenteditable]")) return;
  const key = event.key.toLowerCase();
  if (key==="z" || key==="y") {
    event.preventDefault();
    if (key==="y" || event.shiftKey) restoreHistory(redoHistory,history);
    else restoreHistory(history,redoHistory);
  }
});
editorControls();

const english = new Map(Object.entries({
  "語言":"Language","深色模式":"Dark mode","淺色模式":"Light mode","輸入與排版":"Input and layout",
  "內建案例":"Examples","選擇案例":"Select an example","輸入格式":"Input format","自動判斷 JSON":"Auto-detect JSON",
  "原始 Process Algebra":"Raw Process Algebra","上傳 JSON":"Open JSON","JSON 編輯器":"JSON editor",
  "貼上 SMD 或已解析的 Mock Converter JSON":"Paste SMD or resolved Mock Converter JSON",
  "原始 Process Algebra 需要確認後的 R、S 組 Converter。目前可使用 SMD 或已解析的 Mock JSON。":"Raw Process Algebra requires the R/S Converter. Use SMD or resolved Mock JSON.",
  "排版引擎":"Layout engine","Phase 3 拓樸":"Phase 3 Topology","進階最佳化":"Advanced","原始基準":"Legacy",
  "方向":"Direction","水平":"Horizontal","垂直":"Vertical","搜尋模式":"Search mode",
  "可試用另一個方向":"Try both orientations","產生 Phase 3 對照":"Compare with Phase 3",
  "密集平面圖比較 ELK":"Try ELK for dense flat graphs","排版參數":"Layout parameters",
  "節點間距":"Node spacing","分層間距":"Layer spacing","區域邊距":"Region padding","連線淨距":"Edge clearance",
  "交叉成本":"Crossing cost","轉折成本":"Bend cost","標籤淨距":"Label clearance",
  "下載排版設定":"Download settings","載入排版設定":"Open settings","生成狀態機圖":"Generate diagram",
  "驗證":"Validate","格式化 JSON":"Format JSON","取消運算":"Cancel","驗證與診斷":"Validation and diagnostics",
  "圖形預覽":"Diagram preview","縮小":"Zoom out","放大":"Zoom in","適合畫面":"Fit","重設":"Reset view","全螢幕":"Fullscreen",
  "拖曳節點":"Drag states","鎖定節點":"Lock state","解除鎖定":"Unlock state","收合複合狀態":"Collapse composite",
  "展開複合狀態":"Expand composite","復原":"Undo","重做":"Redo","恢復自動排版":"Restore automatic layout",
  "選擇案例或貼上 JSON，然後生成狀態機圖。":"Choose an example or paste JSON, then generate the diagram.",
  "顯示全圖":"Show full diagram","搜尋與狀態階層":"Search and hierarchy","搜尋名稱、觸發、守衛或效果":"Search names, triggers, guards or effects",
  "搜尋狀態或轉移":"Search states or transitions","匯出":"Export","下載":"Download","SVG（完整階層）":"SVG (complete hierarchy)",
  "品質報告 JSON":"Quality JSON","排版品質":"Layout quality","選取的圖元":"Selected item","點選狀態或轉移查看資料。":"Select a state or transition to inspect it.",
  "工作區":"Workspace","下載工作區":"Download workspace","還原裝置上的工作區":"Restore local workspace",
  "清除裝置副本":"Clear local copy","開啟工作區 JSON":"Open workspace JSON","只在這部裝置自動保存":"Autosave on this device only",
  "下載離線引擎":"Download offline engine","正在下載離線資源…":"Downloading offline assets…","離線引擎已就緒。":"Offline engine is ready.",
  "離線下載未完成。":"Offline download did not complete.","已離線。":"Offline.","離線":"Offline","線上":"Online",
  "Python 引擎會在第一次操作時載入。":"The Python engine loads on first use.",
  "節點重疊":"Node overlaps","標籤碰撞":"Label collisions","連線交叉":"Edge crossings","連線穿過非端點節點":"Edge–node intersections",
  "共線長度":"Overlapping edge length","斷開錨點":"Disconnected anchors","轉折數":"Edge bends","連線總長":"Total edge length",
  "圖面面積":"Area","排版時間（ms）":"Layout time (ms)","繪圖時間（ms）":"Render time (ms)",
  "完整管線（ms）":"Pipeline time (ms)","語意資料與 ID 完整":"Semantic data and IDs preserved",
  "標籤遮住轉移":"Label–path collisions","無效路徑":"Broken paths","完整管線":"Pipeline","個候選":"candidates",
  "通過":"Pass","失敗":"Fail","分數":"Score","未命名":"Unnamed","名稱":"Name","種類":"Kind","行為":"Behaviors","互動原文":"Original interaction",
  "線性序列":"Linear sequence","守衛分支":"Guarded branches","巢狀複合狀態":"Nested composites",
  "課堂快速入門":"Classroom quick start","本次結果":"Current result","瀏覽器 Python":"Browser Python",
  "選一個案例生成圖形。點選狀態或轉移可檢查看到的語意與原始資訊。":"Generate an example, then select a state or transition to inspect its source information.",
  "切換到 Auto／Hybrid 並生成後，可展開「排版品質」比較候選，或下載圖形與 JSON。":"Try Auto / Hybrid and open Layout quality to compare candidates. Download the diagram or JSON.",
  "正交區域":"Orthogonal regions","偽狀態與邊界點":"Pseudostates and boundary points",
  "請先輸入 JSON。":"Enter JSON first.","正在驗證及生成圖形…":"Validating and generating…","正在處理輸入…":"Processing input…",
  "已取消運算。":"Operation cancelled.","這次操作失敗。預覽保留上一份圖形。":"Operation failed. The previous preview is still available.",
  "操作失敗，請查看診斷。":"Operation failed. See the diagnostics.","JSON 已格式化。":"JSON formatted.",
  "Semantic Model 驗證完成。":"Semantic Model validated.","狀態機圖已生成。":"Diagram generated.",
  "初始化 Python Worker":"Starting Python worker","正在載入 Python 與 WebAssembly":"Loading Python and WebAssembly",
  "正在載入 Python 套件與驗證依賴":"Loading Python and validation packages",
  "正在初始化驗證及排版模組":"Initializing validation and layout modules",
  "正在載入 Pretty SMD 套件":"Loading Pretty SMD","正在載入 Schema 驗證依賴":"Loading schema dependencies",
  "Python 引擎就緒":"Python engine ready","驗證模型":"Validating model","計算排版":"Computing layout","產生 SVG":"Rendering SVG",
  "計算品質":"Evaluating quality","計算 Phase 3 對照":"Calculating Phase 3 baseline","載入選配 ELK 並計算平面排版":"Running the optional ELK engine",
  "未套用變更。":"Change was not applied.","此節點已鎖定。":"This state is locked.","重新路由":"Rerouted",
  "其他節點位移":"Displacement of other nodes","已隱藏的內部節點":"Hidden internal nodes","內部轉移":"Internal transitions",
  "裝置無法保存此工作區，請下載檔案。":"This device could not save the workspace. Download it instead.",
  "無法開啟工作區。":"Could not open workspace.","工作區已載入。":"Workspace loaded.","工作區檔案超過 1 MiB。":"Workspace exceeds 1 MiB.",
  "無法匯出 PNG。":"Could not encode the diagram as PNG.",
  "預覽操作":"Preview controls","版本比較":"Version comparison","編輯圖形":"Edit diagram",
  "可拖曳及縮放的狀態機圖":"Pannable and zoomable diagram","圖形縮圖":"Diagram minimap",
  "Benchmark · 50 節點稀疏圖":"Benchmark · 50-node sparse graph",
  "Benchmark · 25 節點循環":"Benchmark · 25-node cyclic graph",
  "Benchmark · 25 節點自迴圈":"Benchmark · 25-node self-loop graph"
}));
const translations = [];
function tr(message) {
  return document.documentElement.lang==="en" ? (english.get(message) || message) : message;
}
function localize() {
  for (const set of translations) set();
  for (const option of el("example").querySelectorAll("[data-translate]")) option.textContent = tr(option.dataset.translate);
  if (displayed) showVersion(displayed===current.baseline);
  editorControls();
  el("theme").textContent = tr(document.documentElement.dataset.theme==="dark" ? "淺色模式" : "深色模式");
}
const translated = document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
while (translated.nextNode()) {
  const item = translated.currentNode;
  const original = item.nodeValue;
  const message = original.trim();
  if (english.has(message)) translations.push(()=>{ if (item.isConnected) item.nodeValue = original.replace(message,tr(message)); });
}
for (const item of document.querySelectorAll("[aria-label],[placeholder]"))
  for (const attr of ["aria-label","placeholder"]) {
    const value = item.getAttribute(attr);
    if (english.has(value)) translations.push(()=>item.setAttribute(attr,tr(value)));
  }
const preferred = new URLSearchParams(location.search).get("lang");
if (preferred==="en") { document.documentElement.lang = "en"; el("language").value = "en"; }
el("language").addEventListener("change",()=>{
  document.documentElement.lang = el("language").value;
  localize();
});
localize();

if (inBrowser && "serviceWorker" in navigator) {
  el("offline").hidden = false;
  const offlineStatus = message=>{ el("offline-status").textContent = tr(message); };
  const ready = registration=>new Promise((resolve,reject)=>{
    if (registration.active?.state==="activated") { resolve(); return; }
    const worker = registration.installing || registration.waiting || registration.active;
    if (!worker) { reject(new Error("Missing service worker")); return; }
    const timer = setTimeout(()=>reject(new Error("Offline download timed out.")),120000);
    const changed = ()=>{
      if (worker.state==="activated" || worker.state==="redundant") {
        worker.removeEventListener("statechange",changed);
        clearTimeout(timer);
        if (worker.state==="activated") resolve(); else reject(new Error("Offline download failed."));
      }
    };
    worker.addEventListener("statechange",changed);
    changed();
  });
  el("offline-download").addEventListener("click",async ()=>{
    const button = el("offline-download");
    button.disabled = true;
    offlineStatus("正在下載離線資源…");
    try {
      const registration = await navigator.serviceWorker.register("./sw.js",{updateViaCache:"none"});
      await ready(registration);
      offlineStatus("離線引擎已就緒。");
    } catch { offlineStatus("離線下載未完成。"); }
    finally { button.disabled = false; }
  });
  navigator.serviceWorker.getRegistration().then(registration=>{
    if (registration?.active) offlineStatus(navigator.onLine ? "離線引擎已就緒。" : "已離線。");
  }).catch(()=>{});
  window.addEventListener("offline",()=>offlineStatus("已離線。"));
}
