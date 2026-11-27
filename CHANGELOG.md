# Changelog

## 0.1.0 Experimental

- 提供共享 Python SDK、CLI、可安裝 wheel 及本機 Web App，從 SMD 或已解析 Mock JSON 生成 SVG 與結構化產物。
- 修正 Composite 背景遮住轉移、UML 偽狀態圖元、輪廓錨點、邊界連接點及區域標籤留白。
- 增加以 SCC 分層的階層排版及可調整的正交路由。保留原始引擎方便比較。
- 提供 13 組可重現的評估、整合基準、實際瀏覽器與像素測試，以及 CLI／Web 測試。
- SMD 和 Layout Schema 保持 0.1.0-draft。正式 Process Algebra Converter 待取得可執行版本與語意樣本。

## 整合基準

- Group F 三個原始模組在 [PR #4](https://github.com/yyyunx/pretty-state-machine-diagrams/pull/4) 完成整合，包含 Model 驗證、遞迴已解析 Mock、排版及 SVG 輸出。
