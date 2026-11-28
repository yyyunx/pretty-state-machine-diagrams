# Phase 5–7 實測

實測使用 Windows 11、Native Python 3.13.12、Chromium、Pyodide 0.29.3、elkjs 0.11.0 及 Graphviz 16.1.2。這批資料記下各環境的個別時間。原生 benchmark 逐筆開隔離程序，執行一次，每筆排版預算 8 秒，含程序啟動時限 10 秒。瀏覽器壓測從同一 Pages 子路徑的靜態環境執行，記錄 Worker 結果、逾時與診斷。

## Browser／Native 一致性

43 組通過。包含既有 13 組、5 組固定種子 holdout 的 Topology 測試，以及 5 組代表性案例各別測 Legacy、Advanced Fast／Balanced／Quality、Hybrid。驗證完整 Model、Layout、SVG 結構、ID 和幾何品質。同源數值座標容差為 `1e-5`，時間等執行環境數值分開記錄。

| 瀏覽器量測 | 結果 |
| --- | ---: |
| Worker 冷啟動（互動 smoke） | 6,223.9 ms |
| 首次生成端到端（parity） | 6,214.7 ms |
| 後續 42 次生成的端到端中位數 | 335.0 ms |
| Worker 外額外延遲中位數 | 0.7 ms |
| WASM 線性記憶體觀察值 | 30,212,096 bytes |
| Pyodide runtime 與驗證依賴 | 12,685,275 bytes |
| 測試用 Python wheel | 101,303 bytes |

WASM 數字為請求完成時可讀的線性記憶體配置，整個 Chromium 行程的記憶體仍需另行量測。頁面在密集案例運算期間繼續處理 animation frames。展示、匯出、取消、逾時後恢復與離線重載也各以 Chromium 驗收過。

[一致性原始資料](parity.json) · [瀏覽器外部引擎量測](external.json) · [實際編輯畫面](editor.png)

## Hybrid 品質與密集圖

原生量測涵蓋 18 組模型、8 條排版路徑，共 144 筆。Graphviz 有 5 筆明確不支援，Legacy 和 Advanced Balanced 各有一次逾時。Hybrid 和 Hybrid + Graphviz 各完成 18 組。完整結果均保留。下表使用同一獨立密集案例 `holdout-dense-17`，含 17 節點、61 條轉移。

| 執行環境／引擎 | 交叉 | 轉折 | 面積 | 排版或請求時間 |
| --- | ---: | ---: | ---: | ---: |
| Native Legacy | — | — | — | 逾時 |
| Native Topology | 802 | 159 | 550,121 | 1,043 ms |
| Native Advanced Fast | 657 | 225 | 574,131 | 751 ms |
| Native Advanced Quality | 657 | 225 | 574,131 | 1,330 ms |
| Native Hybrid | 657 | 225 | 574,131 | 1,930 ms |
| Native Graphviz | 91 | 149 | 8,705,576 | 180 ms |
| Native Hybrid + Graphviz | 91 | 149 | 8,705,576 | 2,090 ms |
| Chromium ELK | 110 | 168 | 1,982,612 | 679 ms（請求） |
| Chromium Hybrid + ELK | 110 | 168 | 1,982,612 | 5,410 ms（請求） |

在這個案例，選配引擎用較大面積換取較少交叉。Hybrid 的搜尋會花時間比較候選。各項成本在有效候選間正規化，單一指標的最大貢獻受它的權重限制。正交案例在 ELK 回傳明確診斷，Hybrid 由內建候選完成。這些結果只代表本批模型及環境。 [原生完整數據](native-hybrid.json)

## 10 至 500 個稀疏節點

各規模測 Topology、三個 Advanced 模式、Hybrid 共 30 筆。10、25、50、100 節點兩種執行環境均完成。250 及 500 節點的 Topology 在兩種環境都逾時。500 節點時，瀏覽器的 Balanced、Quality 也逾時，Fast 約 9.2 秒、Hybrid 約 9.8 秒且產出成功。成功與失敗都有原始紀錄。 [壓測資料](stress.json)

## 增量路由

Chromium 真實拖曳線性案例中的 State。完整生成管線 57.3 ms，拖曳後的 Python 排版、品質與更新工作 40.8 ms，兩者含括的階段略有不同。移動 1 個節點、更新 2 條路徑，其餘節點位置逐一比對皆維持原座標。交叉、碰撞、斷錨及節點穿越維持 0，轉折從 0 增至 4。另以單元測試確認新位置阻擋其他轉移時也會重布那條路徑，且鎖定與區域邊界會阻止非法移動。這次測試觀察到位移與路由範圍，通用加速幅度仍需更多案例量測。

[路由數據](incremental.json) · [完整 Hybrid SVG](nested-hybrid.svg) · [同案例收合 SVG](nested-collapsed.svg) · [ELK SVG](linear-elk.svg)

## 重現

```bash
pretty-smd benchmark-advanced --suite reference --output-dir out/native --timeout 8 \
  --dot /path/to/dot --engine legacy --engine topology --engine advanced-fast \
  --engine advanced-balanced --engine advanced-quality --engine hybrid --engine hybrid-dot --engine graphviz
P57_STRESS=1 node tests/browser_runtime.cjs dist out/browser
```

網站與 Chromium 建置見 [部署指南](../../docs/DEPLOYMENT.md)。正式 Pages 發布、跨瀏覽器驗證及 R、S Converter 狀態以該版 PR 的最新驗收為準。
