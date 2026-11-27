# 進階排版操作與限制

~~~sh
pretty-smd generate examples/basic.smd.json --algorithm advanced --mode fast --output diagram.svg
pretty-smd generate examples/basic.smd.json --algorithm advanced --mode quality --timeout 5 --allow-rotate --quality-output quality.json
pretty-smd benchmark-advanced --suite all --timeout 4 --dot /path/to/dot --output-dir benchmark-output/phase4
~~~

`topology` 是預設，也就是 Phase 3 放置與路由。13 份 Phase 3 Layout JSON 的欄位與路徑結構逐一核對，跨 Python 版本的座標容差為 10⁻⁷ SVG 單位。Legacy 仍可使用 `--algorithm legacy`。Advanced 是實驗選項，適合想交換時間換取更少交叉或較短線長時使用。

| 模式 | 候選分配 | 搜尋工量上限 |
| --- | --- | ---: |
| Fast | 一組索引式路由。由 25 個頂點起試用 SCC 內分層。 | 320,000 |
| Balanced | 增加緊湊間距、反向中位數掃描、不同路由順序及有限重布線。 | 690,000 |
| Quality | 另外嘗試增加淨距及不同 SCC 配置。 | 1,250,000 |

高密度或至少 100 個頂點的案例減少候選數。使用 `--allow-rotate` 才能在允許搜尋的規模內試另一個方向。各模式在固定工量內採用同一輸入，路徑與選擇可重現。指定的牆鐘上限用於取消並診斷，實際經過時間記在品質報告中。

Python 可透過 `generate(model, algorithm="advanced", mode="balanced", timeout=5)` 取得 SVG、Layout 及 `quality["optimization"]`，或用 `optimize(model, options, mode="quality")` 直接取得 Layout、指標及候選資料。搜尋超限時可捕捉 `BudgetExceeded`。幾何候選不合規會回報 `LayoutError`，非法 UML 由 Model 驗證回報。

Web App 可切換階段版本、比較即時品質、按名稱或轉移內容搜尋，選取節點時會高亮其轉移。區域階層可在搜尋面板展開或收合。大型案例可從 minimap 定位畫面。排版參數可下載及重新載入 JSON。視圖操作保留原本 Model；由於變更節點座標還需要同步檢查所有邊與區域限制，首版進階功能維持自動揀選和參數備份。

本機服務 Advanced 與 Topology 的入口上限為 120 個頂點、300 條轉移；Legacy 入口為 48 個頂點、96 條轉移。這些是輸入上限，實際能完成的規模取決於密度與時間預算。CLI 及 SDK 可接收至 500 個頂點、2,400 條轉移。用 `benchmark-advanced` 跑大型壓測時，每次測量會在獨立程序中執行，超時及其他失敗均寫入報告。

## 靜態圖例

~~~sh
python scripts/build_gallery.py --output dist
python -m http.server 8000 --bind 127.0.0.1 --directory dist
~~~

靜態圖例顯示預生成 SVG、品質比較及效能曲線。Pages workflow 在 PR 建立可下載的靜態產物，正式部署分支是 `main`，來源設定為 GitHub Actions。原始模型可用本機 CLI、SDK 或 Web App 即時產生。 [GitHub Pages 來源設定](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)

## 第三方元件

Python 套件沿用 jsonschema。此環境的 jsonschema、attrs、jsonschema-specifications、referencing、rpds-py 發行中繼資料標示 MIT。Graphviz 16.1.2 為外部比較執行檔，Playwright 用於 Chromium 驗證，Matplotlib 用於生成效能曲線。這三者都由其各自發行來源安裝。 [Graphviz EPL-2.0](https://graphviz.org/license/) · [Playwright Apache-2.0](https://github.com/microsoft/playwright/blob/main/LICENSE) · [Matplotlib 授權](https://matplotlib.org/stable/project/license.html)
