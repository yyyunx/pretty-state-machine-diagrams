# Experimental v0.3.0 發行草稿

## 功能

- 無須安裝 Python 的靜態網站。Web Worker 使用固定版 Pyodide 執行共享 Python 管線。首次操作載入引擎，支援取消、逾時重啟和選配離線快取。
- 保留 Legacy、Topology 及 Advanced，加入 Auto／Hybrid、選配 ELK 平面排版和原生 Graphviz。課堂案例及 Gallery 可比較同一份模型。
- 支援拖曳、增量路由、鎖定、Undo／Redo、收合及工作區。匯出 SVG、PNG、SMD、Layout、品質 JSON 和排版設定。
- 原生 CLI、Python SDK、loopback Web App 及 UTF-8 `0.1.0-draft` 輸出繼續適用。

## 驗收與產物

- PR #7 提供靜態網站檔、瀏覽器驗收產物及 Windows、macOS、Linux wheel。查驗產物所屬的 CI 和 commit。
- 發行前確認以保留 commit 歷史的方式通過 PR #5、#6、#7 審查，從核准的 `main` 執行 Pages 工作流，並檢查公開網址的瀏覽器驗收。
- 正式 Process Algebra 仍需 R、S 組提供 Converter。ELK 的範圍為已驗證的平面模型，Graphviz 適用原生選配。

## 發布條件

這份文件供 Group F 審查。正式發行、標籤與套件發布需共同作者確認。第三方 Runtime 和選配引擎的授權與來源已隨網站附上。 [第三方依賴](BROWSER_RUNTIME.md#第三方版本與授權)
