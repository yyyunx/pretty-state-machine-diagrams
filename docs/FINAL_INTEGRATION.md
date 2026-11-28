# 最終整合與驗收

## PR 依賴與審查

| PR | 比較基線 | 主要變更 |
| --- | --- | --- |
| [#5](https://github.com/yyyunx/pretty-state-machine-diagrams/pull/5) | `main` | UML 圖元與錨點、拓樸排版、CLI／SDK、本機 Web |
| [#6](https://github.com/yyyunx/pretty-state-machine-diagrams/pull/6) | `feature/project-optimization` | 進階搜尋、規模與 Graphviz 基準、Gallery、跨平台 wheel |
| [#7](https://github.com/yyyunx/pretty-state-machine-diagrams/pull/7) | `feature/advanced-optimization` | 瀏覽器 Python、Hybrid、互動編輯、離線、Pages 及跨瀏覽器驗收 |

在 GitHub 檢查各 PR 最新 head 的組員核可和 CI。先以 **Create a merge commit** 合併 #5，接著把 #6 的 base 改到 `main` 並重驗差異及 CI。合併 #6 後對 #7 重複同一流程。合併前確認上游 PR 的 head 仍是下游的祖先，比對現有變更與最新 CI。這種方式保留所有組員原始 commit。最後核對 `main` 可追溯到三張 PR 的 head。

## Pages 驗收

管理員／維護者在 Settings → Pages → Build and deployment → Source 選 GitHub Actions。工作流先建置同一份網站並跑 Chromium、Firefox、WebKit 和 Edge。通過後，`main` 才能部署同一份 artifact，再對公開 URL 驗收 Chromium、Firefox、WebKit。正式網址成功後再更新 README 的 Live Demo。

裝置驗收使用桌面視窗、390 × 844 的手機尺寸和 820 × 1180 的平板尺寸，並以觸控模擬檢查案例選擇、縮放及適應畫面。Edge 案例使用 Microsoft Edge。如果 macOS runner 允許 Apple SafariDriver，原生 Safari job 驗證案例生成、Hybrid 切換、SVG 及 PNG 內容。iOS Safari 真機留待實機驗收。

## 交付物

[課堂快速入門](TEACHER_QUICKSTART.md) · [Experimental 發行草稿](RELEASE-0.3.0.md) · [Converter 交接](../src/model/CONVERTER_HANDOFF.md) · [部署指令](DEPLOYMENT.md)
