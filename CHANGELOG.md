# Changelog

## 0.3.0 Experimental

- Pyodide Web Worker 在瀏覽器執行原有 Python 引擎。支援真實階段進度、取消、逾時重建、JSON 驗證及 PNG 匯出。
- Auto／Hybrid 依圖形特徵安排候選，確認合法幾何後依正規化目標挑選結果。ELK 可作為瀏覽器選配平面引擎，Graphviz 保留原生選配入口。
- 支援拖曳、增量路由、單一或多個節點鎖定、收合、復原、重做及工作區 JSON。
- 加入中英文介面、選配裝置自動保存、離線引擎、Gallery 一鍵開啟案例及 Hybrid 比較。
- GitHub Pages 在 Chromium 驗收後由核准的 main 工作流發布。原生 wheel、CLI、SDK 及 SMD／Layout Schema 維持相容。

## 0.2.0 Experimental

- 增加 Advanced Fast、Balanced、Quality，多目標比較的兩種基準仍可使用。
- 增加空間索引、SCC 內部分層、有限重布線、同側自迴圈、標籤避線及邊界點方向限制。
- 增加 10 至 500 頂點的隔離壓測、獨立案例、Graphviz 比較、失敗紀錄及效能曲線。
- Web 增加版本比較、搜尋與階層、轉移高亮、minimap 及排版設定備份。
- 發行檢查加入 Windows、Linux、macOS 的 wheel 安裝，並提供靜態 Gallery。

## 0.1.0 Experimental

- 提供共享 Python SDK、CLI、可安裝 wheel 及本機 Web App，從 SMD 或已解析 Mock JSON 生成 SVG 與結構化產物。
- 修正 Composite 背景遮住轉移、UML 偽狀態圖元、輪廓錨點、邊界連接點及區域標籤留白。
- 增加以 SCC 分層的階層排版及可調整的正交路由。保留原始引擎方便比較。
- 提供 13 組可重現的評估、整合基準、實際瀏覽器與像素測試，以及 CLI／Web 測試。
- SMD 和 Layout Schema 保持 0.1.0-draft。正式 Process Algebra Converter 待取得可執行版本與語意樣本。

## 整合基準

- Group F 三個原始模組在 [PR #4](https://github.com/yyyunx/pretty-state-machine-diagrams/pull/4) 完成整合，包含 Model 驗證、遞迴已解析 Mock、排版及 SVG 輸出。
