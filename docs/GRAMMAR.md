# 修訂 Grammar 與 SMD 對應草案

下表依老師的修訂 Grammar 與任務對話整理。欄位描述的是行為與可能的圖形結構。確切的降階規則、完整語法與錯誤處理仍需以老師案例及 R、S Converter 輸出驗證。

| Grammar | 對 SMD 的意義 | 尚待確認的轉換規則 |
| --- | --- | --- |
| `iss . s`、`iss strict s` | interaction 前綴的嚴格接續。interaction 可對應轉移及其標記。 | 由 `i` 與 GIT 決定 trigger、guard、effect 的資料來源與組合方式。 |
| `i seq i` | interaction 的弱順序，保留必要的事件順序與允許的不同執行次序。可用無顯示名稱的中間節點表示。 | 等 Converter 的事件模型與老師案例驗證可允許的順序。 |
| `s >> s` | 依序合成完整的程序運算元，保留各運算元及其完成條件。 | 指定 `C`、`©`、`0`、`◉` 所允許的接續。 |
| `s alt s` | 擇一分支，保留順序及 guard。可能是狀態的多條離開轉移，也可能涉及 Choice 或 Junction。 | 選擇何種圖形、二條件標註和後續多分支的關聯。 |
| `s par s` | 併行，保留各分支和階層。明確的 Orthogonal Regions 可由同一 Composite State 之下的多個 Region 表示。 | 何時生成或採用區域、如何完成及同步。 |
| `ref A` | 引用具名程序，保留被引用的識別資訊。 | 名稱作用域、缺失參照、遞迴和 UML Submachine 或展開的規則。 |
| `([attribs]: expr)` 與 `(expr)` | 屬性可標註具名 State、Composite State、Region、defer 和 invariant。括號保留分組。 | 如何由語法位置辨認狀態、區域、純分組及其屬性歸屬。 |
| `entry(...)`、`exit(...)`、`do(...)` | 分別表示狀態的進入、離開與執行中行為。 | 語法中冒號兩側的歸屬，複合 behavior 如何綁定 State。 |
| `defer[e, ...]`、`invariant[cond]` | 保留延後處理的事件及狀態不變式。 | 事件與條件的資料結構、同類屬性重複時的診斷。 |
| `pseudo(initial/shallowH/deepH/join/entryP/exitP/...)` | 對應 Initial、Shallow/Deep History、Join、Entry/Exit Point 等偽狀態。顯式 `choice`、`junction`、`fork`、`terminate` 各有獨立圖元。 | 各種類的 outgoing expression、邊界歸屬、history 預設路徑與驗證規則。 |
| `◉`、`0`、`C`、`©` | 課程範例以 `◉` 表示完成，SMD Model 可表達 Final State。其他標記應保留各自的語意。 | 完成範圍、每個標記與 UML 頂點的映射、何時可接續。 |
| `raise`、`(loop...:expr)`、其他 Combined Fragment | 保留事件產生、迴圈條件及上下限。跨圖種構造具各自的行為約束。 | 確認 SMD 支援邊界及來源診斷，包含獨立的 `fork(...)`、`join[cond]`、AD 屬性與 SD fragments。 |

Grammar 的範例和 production 要分開檢查。公開說明的簡寫把 `i` 直接放在 `>>` 兩側，修訂 production 則要求 `s`。`alt` 的可選條件出現在第一個分隔處，後續分支條件、`i`、`cond`、`e`、`A` 等 token 的定義需向來源確認。

論文的舊範例在一致性分析情境下簡化了部分弱順序。此專案的語意驗收要求保留原始行為，完整保留 `seq` 的允許行為，拆分或合成轉移須有可比對的案例。把多層結構降階到 ITG 時，另外保有分組、命名、區域和原始轉移資料，才能產出原意一致的 SMD。
