# 使用說明

## 安裝

使用 Python 3.10 以上，建議在虛擬環境內執行 `python -m pip install .`。若取得 CI 提供的 wheel，可使用 `python -m pip install <wheel 路徑>`。可在任何目錄執行安裝後的 `pretty-smd`，也可執行 `python -m pretty_smd`。

## CLI

~~~sh
pretty-smd validate examples/basic.smd.json
pretty-smd generate examples/basic.smd.json --output diagram.svg \
  --smd-output model.json --layout-output layout.json --quality-output quality.json \
  --direction vertical --set layer_spacing=72
pretty-smd generate tests/model/cases/mock-converter-p2.json --case nested --format mock --output nested.svg
pretty-smd benchmark --output-dir benchmark-output --repeats 3 --memory
pretty-smd serve --port 8000
~~~

命令可寫在一行。在 PowerShell 使用時，請將跨行的反斜線續行改為一行。省略 `--output` 時，SVG 輸出至 stdout。驗證成功時回傳 JSON 及警告。驗證或路由失敗時回傳 exit code 2，診斷送至 stderr。預設檢查 UML 規則。若只要 Schema 與引用檢查可使用 `--structural`。

自動模式接受單一 SMD 或 Mock JSON。fixture 包使用 `--case`。Legacy 引擎保留原有放置及路由。Topology、Advanced 和 Hybrid 可用 `--direction` 及重複的 `--set`。見 [API](API.md)。

## Web App

執行 `pretty-smd serve`，在瀏覽器造訪 [127.0.0.1:8000](http://127.0.0.1:8000)。預覽會先載入正交案例。可選其他案例、貼上 JSON 或選擇本機檔案，再按「生成狀態機圖」。檢視區可拖曳、縮放、適合畫面、重設及全螢幕。點擊狀態或轉移，或使用 Tab 加 Enter，可查看原始行為與欄位。品質與驗證內容各自可展開。

下載對應最後一次成功生成的圖與設定。修改輸入後，先生成再下載。Web 伺服器只接受本機請求，檔案內容在本機送入 Python。一般引擎上限為 500 個頂點、1,200 條轉移。Legacy 上限為 48／96。可直接下載 SVG 或 PNG。瀏覽器版免啟動本機伺服器。編輯、工作區、離線下載及 Pages 發布見 [瀏覽器操作](BROWSER_RUNTIME.md) 和 [部署](DEPLOYMENT.md)。

## 靜態展示

`demo/index.html` 引用 repo 中預生成的 SVG。靜態網站建置會把它放到 `/gallery/`，加入 Hybrid 比較及可直接載入同一個案例的編輯器連結。
