# R、S 組 Converter 交接提問單

供老師及 R、S 組逐項確認。下列是 Group F 產生狀態機圖所需的最小資訊，外部資料格式與 Grammar 語意仍待答覆。

## 最小輸入

| 由 Converter 提供 | Group F 用途 |
| --- | --- |
| 可試用的 repository 或可執行版本、Grammar 版本、一次呼叫的輸入輸出，以及主要程序或模型的穩定識別。請給一份實際線性例與一份包含兩個 Region 的階層例。 | 選用可重現的版本及來源，確保 Layout 與 Renderer 取得同一份 SMD Model 與相符的 Layout Data。 |
| 有序的程序、State 和 Region 樹。標出明確名稱、容器類型、頂點類型、偽狀態種類、各 Region 隸屬與正交關係、連線端點及擁有的 Region。前後參照使用可在本模型內解析的鍵。 | 重建同一張圖，保留跨層連線、匿名元素、Fork／Join、History、入口與出口的從屬。顯示名稱不能作為參照鍵。 |
| 原始 `entry`、`exit`、`do`、`defer`、`invariant` 及綁定對象。每條轉移的 trigger、guard、effect 與原始互動標記或 GIT 參照。選填資料用明確的缺省方式標示。 | 保存原文字元、順序與欄位區別，辨認沒有 trigger 的轉移。GIT 若含 caller、callee、參數或呼叫／回傳資料，請提供可用互動 ID 查回的表。 |
| 已解析控制流的 entry、exit、每條分支續接與 guards、迴圈回邊、平行同步、完成範圍及程序引用結果。對無法解析的節點提供原始 token、程序或檔案及文字範圍。 | 只將語意已確認的行為轉成頂點與轉移。對合法但未決的來源、缺少的定義與語法錯誤保留不同診斷。 |

Group F 目前的 Python 接縫為 `ConverterAdapter.adapt(source) -> Model`，回傳交給 Builder 的明確 SMD draft，或以 `ModelError` 回報診斷。外部可以提供結構化 AST 或已解析行為圖，再由薄 Adapter 轉換。若只提供平坦 ITG，請附可還原階層、命名、互動與來源的對照。共同輸出仍使用 UTF-8 `0.1.0-draft`。導入前需確認各份獨立模型輸出的 `id`，避免將不同版本的 Model 與 Layout Data 配對。

## 請逐例確認 Grammar

以下 `i1`、`i2`、`i3` 代表已定義的不同 interaction，`g1`、`g2`、`g` 代表條件。請回覆最小可觀察事件次序或預期 SMD 結構。若例子語法有誤，請附最小正確寫法。

| 主題 | 最小輸入 | 需確認的行為 |
| --- | --- | --- |
| 嚴格與弱順序 | `i1 strict i2 . ◉`、`i1 seq i2 . ◉` | 給定不同的 caller／callee，請各列允許與禁止的發送、接收次序。`.` 和 `strict` 的差異為何？如何辨識一條轉移的 trigger、guard 和 effect？ |
| 完成與續接 | 單獨 `0`、`◉`、`C`、`©`；各置於 `>> (i1 . ◉)` 左方 | 哪些表示阻塞、整機或 Region 完成、續接？哪些允許右側執行？何時產生 FinalState？ |
| 多分支 guard | `(i1 . C) alt [g1, g2] (i2 . C) alt (i3 . C)` | 兩個條件分屬哪些分支？第三分支、同時成立、全部不成立時如何處理？何時由來源明確要求 Choice 或 Junction？ |
| 平行與同步 | `((i1 . C) par (i2 . C)) >> (i3 . ◉)`；`(fork(i1 . C, i2 . C) >> join[g]) >> (i3 . ◉)` | 何時建立正交 Region？各分支何時算完成，`i3` 可在哪些情況開始？帶條件的 `join` 如何和 SMD Join 區分？ |
| 迴圈 | `(loop(0, 2)[g]: i1 . C) >> (i2 . ◉)` | `g` 的判斷時機、最小與最大次數，以及 `i1` 尚未完成時的退出與續接規則。 |
| 程序引用 | `ref A`；`A` 包含 `ref A`；`ref Missing` | `A` 的作用域、缺失與合法遞迴的診斷、應保留子機器或展開的條件，以及如何識別同名的不同宣告。 |
| 狀態屬性與邊界 | `(["Work", defer[e], invariant[g]]: entry(i1: do(i2: exit(i3: ◉))))`；`pseudo(entryP: i1 . C)`、`pseudo(exitP: i2 . C)` | 狀態、Region 與單純分組如何區分？屬性的歸屬與重複規則、邊界點的 owner 及跨層連線如何表示？ |

收到答案後，請附一份可重跑的資料和期望輸出，再將對應行為納入驗收。
