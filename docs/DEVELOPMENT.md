# 開發與驗證

~~~sh
python -m pip install -e .
python -m unittest discover -s tests -v
python -m tests.model.run_end_to_end --output-dir integration-output/suite
pretty-smd benchmark --output-dir benchmark-output --repeats 3 --memory
npm install --no-save --no-package-lock playwright@1.61.1
npx playwright install chromium
node tests/browser_smoke.cjs
~~~

瀏覽器測試需要 Node 22 與 Chromium。若已有瀏覽器，可透過環境變數 `CHROME` 指定執行檔，`PYTHON` 指定 Python，`PLAYWRIGHT_MODULE` 指定已安裝 Playwright，`PRETTY_SMD_TEST_PORT` 覆寫測試埠。測試啟動及關閉自有的 loopback 伺服器，實際操作 UI、驗證匯出與取樣巢狀連線像素。成功畫面輸出至 `integration-output/browser`。

CI 在 Ubuntu 使用 Python 3.10 及 3.13 打包及執行測試，另外跑 Chromium 來檢查 GUI 與 SVG 像素。工作產物包含 wheel、CLI 匯出、端到端案例與截圖。手動建置 wheel 可以執行 `python -m pip wheel --no-deps --wheel-dir dist .`。版本 0.1.0 的 Experimental 構建可先下載試用，正式發布需共同作者同意。

## Layout

`topology.py` 建立每個 Region 的投影圖並計算 SCC。循環折疊只用於排序，分層引用 SCC DAG 最長路徑，同層使用四輪重心掃描。巢狀尺寸由內往外量測。採用本地演算法可以共用既有階層、狀態行為文字與圖元幾何，也保留原始引擎以同一批輸入量測。

`routing.py` 先比較確定性折線候選，成本含線長、轉折、交叉及共線。候選失敗時改用有限網格搜尋，再失敗則回報轉移。`quality.py` 獨立測量輸出，不參與排版。渲染順序依序為容器、區域分隔、轉移、節點圖元及文字，所有入口共用 `src/renderer`。另見 [比較結果](../benchmarks/RESULTS.md)。

## 瀏覽器與輸入邊界

本機 HTTP 服務使用 Python 標準庫。限制 loopback、同來源 Host／Origin、請求大小、連線數及模型大小。靜態資源採固定路徑，伺服器只回傳結果，匯出由瀏覽器下載。序列化轉義來源文字，限制 SVG 幾何的數值。網頁以 CSP 及 SVG 元素白名單防止非預期內容。以內建 Web App 的本機使用為部署範圍。

## 協作

遵循 [Group F 協作規範](COLLABORATION.md)。共同 Schema 維持草案版本；Adapter 引入正式 R、S 組資料前，將真實案例和預期 SVG 納入端到端測試。
