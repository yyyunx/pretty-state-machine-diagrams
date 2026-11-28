# 建置與發布

## 開發或驗收

Python 3.10 以上可執行原生工具。靜態網站的 CI 使用 Python 3.13、Node 22、Playwright 1.61.1 與 Chromium。安裝後在專案根目錄建置。

```bash
python -m pip install .
python -m pip wheel --no-deps --wheel-dir build/wheels .
python scripts/build_browser.py --wheel build/wheels/pretty_smd-0.3.0-py3-none-any.whl --output dist
npm install --no-save --no-package-lock playwright@1.61.1
npx playwright install chromium
node tests/browser_runtime.cjs dist integration-output/browser-runtime
```

Windows PowerShell 可用 `$env:P57_STRESS='1'` 加入 10 至 500 節點的壓測。Bash 可用 `P57_STRESS=1 node tests/browser_runtime.cjs dist integration-output/browser-runtime`。測試自行啟動靜態伺服器並將 `dist/` 掛在 Pages 子路徑，不需啟動 Python server。建立較新版本時使用空的輸出目錄。HTML 走相對路徑，服務須正確傳送 `.wasm` 與 UTF-8。

GitHub Actions 的 `install-free-website` artifact 是完整網站，`browser-runtime-evidence` 包含截圖、SVG、工作區樣本及驗證報告。原生安裝以 integration 工作流的 Windows、Linux、macOS wheel 檢查為準。

## GitHub Pages 正式發布

1. 有倉庫管理權限的成員在 **Settings → Pages → Build and deployment → Source** 選擇 **GitHub Actions**。
2. 依 PR #5、#6、#7 的堆疊審查，依序整合及更新 PR base。正式部署工作等核准後的 `main` 流程。
3. 在 Actions 查看 **Browser-native Python and Pages** 的 build、Chromium 與 deploy jobs。待 deploy 成功後，從 job 提供的 URL 開啟網站。
4. 正式 URL 驗收以 workflow 自動執行。可從具有 Chromium 的環境再執行相同測試，設定 `P57_LIVE` 為部署 URL 並設定 `P57_SMOKE_ONLY=1`。

預期正式網址為 [GitHub Pages](https://yyyunx.github.io/pretty-state-machine-diagrams/)。以 Pages 工作流成功和實際瀏覽器驗收確認發布狀態。

## Experimental 0.3.0 草稿

- 交付同一個 Python wheel、可離線的靜態網站及測試證據。
- 主要變更是 Browser Runtime、Adaptive Hybrid 與 Interactive Editor。原有 CLI、SDK、JSON Schema 和 Gallery 可繼續使用。
- 已確認的入口為 SMD 與已解析 Mock JSON。正式 R、S Converter、Pages 管理設定及正式作者授權仍有外部依賴。
