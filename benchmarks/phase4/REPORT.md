# Phase 4 演算法與效能報告

基準為 Phase 3 `d863145`。Legacy 是最初整合版的放置及路由。三種內建引擎共用現在的 SVG Renderer 及同一版品質指標；測試核對全部 13 份 Phase 3 Layout JSON 的欄位、路徑結構及座標，跨 Python 版本允許 10⁻⁷ SVG 單位的浮點誤差。

[完整 CSV](comparison.csv) · [量測環境及 JSON](comparison.json) · [本機 Web App 畫面](advanced-app.png) · [介面與操作](../../docs/ADVANCED.md)

## 審查與決策

| 範圍 | 實質發現與處置 |
| --- | --- |
| SCC 與層級 | 既有迭代 Kosaraju 和縮點 DAG 最長路徑保留。大型 SCC 若全部落在同一層，跨列路徑容易重疊。Advanced 用有向 BFS 將部分 SCC 內部展開，再依 SCC 所佔層數計算縮點 DAG 的排名；原轉移方向保留。重心和中位數掃描可用於比較。 |
| 路由與邊界 | Phase 3 的 48 頂點 cProfile 中，候選路由呼叫約 59 萬次矩形交集和 31 萬次線段衝突檢查。Advanced 使用格網查詢附近的節點與現有線段、快取路段成本，並對大量跨格線段限制索引分配；局部網格回退有固定上限。Entry／Exit Point 的連線依對方是否位於同容器選內外側。同側自迴圈用兩個獨立端口。 |
| 品質指標 | Phase 3 計數沒有獨立呈現標籤蓋住線段，且會略過無關節點在線段端點接觸的情形。新版獨立測量標籤與轉移交集、折返轉折、幾何交叉與共線，僅豁免同一邏輯頂點共用的端點。像素測試另驗證背景與箭頭的實際次序。 |
| 文字與 hierarchy | 由 Python 測量和 Renderer 共用文字格式，匿名狀態的內部 ID 只用於資料參照，長文字、繁中、Unicode 和特殊符號由生成模型測試。Advanced 保持狀態與 Region 階層，驗證子容器座標與外框連接點。 |
| 輸入與工作上限 | CLI、SDK、Web 共用驗證及輸出。Web 限制模型大小、繪圖時限及四個同時處理的連線，忙碌、超時個別回傳 503、504。以有限與重複 JSON、極深資料、SVG 文字轉義、HTTP 逾量請求及搶佔時限測試。 |

以第一個符合硬性限制的候選各項指標正規化，分母最低為 1。總成本採交叉 12、標籤碰撞 9、標籤遮線 5、穿越節點 14、共線長度 4、總線長 5、轉折 3、面積 2 與計算工量 1。牆鐘時間如實記錄；工量作為執行時間的可重現代理量。模型、節點覆蓋、有限座標、階層、錨點與非法交集先檢查，違反硬性限制的候選不能靠分數勝出。交通量高的連線按初始品質選擇有限重布線，嘗試兩個替代端口後只接受局部代價改善。搜尋是有限啟發法。

## 原 13 組同輸入

環境為 Windows 11、CPython 3.13.12、Intel x64，固定種子 24837。每案每引擎一筆實測，時間為案例加總，並非單次請求或速度保證。壓測壁鐘上限為 4 秒，獨立程序另有最多 2 秒啟動及測量餘量；Legacy／Topology 的量測上限以程序為準。RSS 為每次 Python worker 的峰值工作集，包含直譯器及套件。子程序 Graphviz 的 RSS 不在 Python worker RSS 中。

| 指標 | Legacy | Phase 3 | Fast | Balanced | Quality |
| --- | ---: | ---: | ---: | ---: | ---: |
| 完成 | 13 | 13 | 13 | 13 | 13 |
| 斷開錨點 | 9 | 0 | 0 | 0 | 0 |
| 交叉 | 4 | 2 | 2 | 1 | 1 |
| 不同連線共線長度 | 0 | 1 | 1 | 0 | 0 |
| 標籤遮住轉移 | 26 | 6 | 0 | 0 | 0 |
| 標籤碰撞 | 2 | 0 | 0 | 0 | 0 |
| 轉折 | 64 | 62 | 60 | 62 | 62 |
| 總線長 | 20,775 | 18,963.82 | 18,824.14 | 18,570.44 | 16,868.04 |
| 圖面面積 | 6,165,166 | 4,432,997 | 4,465,372 | 4,421,780 | 4,207,092 |
| 排版合計（ms） | 6,105.66 | 1,368.49 | 980.91 | 2,910.82 | 6,451.01 |

偽狀態案例的交叉由 2 降至 1、共線 1 降至 0，但轉折由 12 增至 14。自迴圈案例轉折由 6 降至 4，線長由 276 降至 123.52。Quality 在三個合成案例將線長縮短約 12.5%，但在 48 頂點案例中排版由 810.18 增至 2,542.80 ms。這些增減一併保留。 [偽狀態 Phase 3](topology/pseudostates.svg) · [偽狀態 Quality](advanced-quality/pseudostates.svg) · [自迴圈 Quality](advanced-quality/self-loop.svg)

## 獨立案例與壓測

5 個事後產生的留出模型涵蓋稀疏、高密度、複雜 SCC、自迴圈及巢狀。三個 Advanced 模式與 Phase 3 均完成 5 例。Balanced 將合計交叉從 939 降到 677，合計共線長度從 137,642.80 降到 31,040.16。留出 SCC 的交叉由 105 降到 20，線長由 13,467.60 降到 4,128.56。其餘高密度結果仍有明顯交叉。Quality 在 5 例留出模型的總體幾何與 Balanced 相同，但時間 4,720.96 vs. 2,718.82 ms。Phase 3 因此維持預設，Advanced 供挑選。 [SCC Phase 3](topology/holdout-cycles-16.svg) · [SCC Quality](advanced-quality/holdout-cycles-16.svg)

每個規模各有 5 種模型，包括稀疏分支合併、密集、複雜循環及 SCC、自迴圈、巢狀與正交交會。巢狀組另含跨層轉移與多語長名。數字為 4 秒設定下完成案例數。

| 頂點 | Phase 3 | Advanced Fast | Advanced Balanced |
| ---: | ---: | ---: | ---: |
| 10 | 5/5 | 5/5 | 5/5 |
| 25 | 5/5 | 5/5 | 5/5 |
| 50 | 4/5 | 5/5 | 4/5 |
| 100 | 2/5 | 4/5 | 4/5 |
| 250 | 0/5 | 3/5 | 0/5 |
| 500 | 0/5 | 0/5 | 0/5 |

250 頂點的 Fast 可完成稀疏、自迴圈和巢狀，三案分別使用約 2.19、3.12、2.06 秒。Fast 成功壓測的最高 worker RSS 是 33,504 KiB。高密度 100 頂點起及 500 頂點模型在四秒設定下均逾時。參考與壓測合計 198 筆，所有逾時和未支援條目都在資料中。曲線只連接成功量測；上方 × 是未完成狀態標記。 [效能曲線](performance.svg)

以相同輸入、Fast 及 18 秒預算另做三次 500 頂點實驗，稀疏 4.93 秒、自迴圈 7.03 秒、巢狀 4.37 秒，均完成。此補充測試涵蓋原先在 250 頂點可完成的三種結構，最高 worker RSS 為 36,924 KiB。 [延長預算的原始資料](extended-budget.json)

## Graphviz dot 比較

使用官方 Graphviz 16.1.2，安裝時驗證官方 SHA-256。Dot 的平面比較使用固定節點尺寸及同一套文字測量，保留原圖邊映射，將輸出路徑轉成折線並把端點對齊共用 UML Renderer 的實際輪廓。曲線需以折線近似，其幾何轉折數與自研正交折線不完全等價。可比較 9 個原案例及 4 個留出案例。比較 Adapter 對巢狀、正交或複合邊界點明確回報不支援，未將這些模型扁平化；這是 Adapter 的範圍。 [Graphviz dot](https://graphviz.org/docs/layouts/dot/) · [ELK Layered 評估依據](https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html)

以四個共同平面留出案例比較，dot 合計 91 處交叉、490.81 ms，Quality 為 677 處、3,763.23 ms；dot 的圖面面積約為 Quality 的 6.1 倍。比較結果保留 dot 的交叉與速度優勢，以及本工具在這組資料的緊湊度。ELK 的階層排版另待量測。所有 dot 的數字與不支援原因均在 CSV。 [dot 的留出 SCC 圖](graphviz/holdout-cycles-16.svg)

## 重現

~~~sh
python -m pip install .
pretty-smd benchmark-advanced --suite all --timeout 4 --dot /path/to/dot --output-dir benchmark-output/phase4
python -m pip install matplotlib==3.10.9
python scripts/plot_phase4.py benchmark-output/phase4/comparison.json benchmark-output/phase4/performance.svg
~~~

`--case` 與 `--engine` 可重複傳入，`--repeats` 可取得個別案例中位數。Graphviz 為選配，省略其執行檔可重跑所有自研比較。 [發行草稿與第三方套件](../../docs/RELEASE-0.2.0.md)
