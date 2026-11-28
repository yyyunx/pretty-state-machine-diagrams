"use strict";

const element = id => document.getElementById(id);
const inRepository = /\/demo\/(?:index\.html)?$/.test(location.pathname);
const folder = inRepository ? "../benchmarks/phase4/" : "benchmarks/phase4/";
let rows = [];
for (const type of ["csv","json"]) element(type).href = folder + "comparison." + type;
const graph = document.createElement("img");
graph.src = folder + "performance.svg";
graph.alt = "稀疏與高密度圖的排版時間。縱軸為對數刻度，× 表示逾時或其他失敗。";
element("curve").append(graph);

function show() {
  const selected = element("case").value;
  const editor = element("edit-case");
  if (editor) editor.href = "../?case=gallery-"+encodeURIComponent(selected);
  for (const figure of document.querySelectorAll("figure[data-engine]")) {
    const engine = figure.dataset.engine;
    const asset = folder + engine + "/" + selected + ".svg";
    const img = figure.querySelector("img");
    const link = figure.querySelector("a");
    const output = figure.querySelector("span");
    const row = rows.find(row => row.case===selected && row.algorithm===engine);
    const available = !row || row.status==="ok";
    img.hidden = !available;
    link.hidden = !available;
    if (available) {
      img.src = asset;
      link.href = asset;
    }
    output.textContent = row && available ? "· 交叉 " + row.edge_crossings + " · 轉折 "
      + row.edge_bends + " · " + row.layout_ms + " ms" : row ? row.reason : "";
  }
}
function zoom() {
  const value = element("zoom").value + "%";
  element("zoom-value").textContent = value;
  for (const image of document.querySelectorAll(".view img")) image.style.width = value;
}
element("case").addEventListener("change",show);
element("zoom").addEventListener("input",zoom);
element("reset").addEventListener("click",() => {element("zoom").value=100;zoom();});
show();
fetch(folder + "comparison.json").then(response => {
  if (!response.ok) throw new Error("讀取失敗");
  return response.json();
}).then(data => {
  rows = data.results;
  element("bench-status").textContent = "共 " + rows.length + " 筆量測，包含 "
    + rows.filter(row => row.status!=="ok").length + " 筆未完成或不支援。";
  show();
}).catch(() => {element("bench-status").textContent = "可使用下方連結讀取完整報告。";});
