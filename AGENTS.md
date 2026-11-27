# Group F 開發規範

- 開始工作前讀取 `README.md`、`docs/`、`schemas/` 與 `groupctl inbox`。採用老師最新說明及修訂 Grammar。
- 共同基礎建設以手寫 JSON Mock 和契約測試驗證。核心實作須等三位成員透過 `groupctl` 確認任務、架構、介面、分工和驗收標準。
- 僅在自己的 `feature/*` 分支維護自己的模組及測試。共用文件、Schema、Mock 與契約測試的變動先取得組內共識，再走 PR。
- 以 `id` 作為內部引用。只有原始資料明確命名的元素可帶 `displayName`。保留原始轉移資訊及每一層區域，語意疑義以 `groupctl ask` 留下問題。
- 完成階段性變更後測試、提交、推送自己的開發分支並開 PR。所有日常變更透過審查合併至 `main`。
- 協作事件透過 [`groupctl`](docs/COLLABORATION.md) 發布，保留任務確認、介面決策、問題、測試與 PR 的對應。勿改寫已發布事件或用他人身分回覆。
