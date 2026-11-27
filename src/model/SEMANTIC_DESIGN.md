# Semantic Model 前置設計

責任範圍為 `feature/semantic-model` 的 `src/model/` 與 `tests/model/`。本文件是個別模組的討論草案，對外契約以 Group F 三方確認為準。共同提案為 `Q-yyyunx-6faf49e280`，待查證的語意與 Converter 問題為 `Q-yyyunx-e2302d4665`。

## 原始資料與解讀原則

語意以課程最新說明及貼出的修訂版 Grammar 為準。論文 *SBC Process Algebra for SysML Model Inconsistency Checking* 的第 III.B–C 節與 Fig. 3 提供舊版運算子、interaction 與初始 ITG 節點的背景。第 IV.A–B 節與 Figs. 4–7 顯示弱順序需要保留多種事件次序，以及 Guarded Interaction Table（GIT）可保存 guard、呼叫與回傳、參數和 effect。論文用於一致性檢查的特例簡化了部分弱順序，本專案的驗收須保留輸入允許的行為。第 V 節的 XML 是論文工具示例。

初始、終止與普通狀態各有結構角色。來源未明確命名時，包括為了表達執行順序或替代路徑所需的中間狀態，都省略 `displayName`。草案可表達不同 Region 中的頂點使用同一顯示名稱，內部 ID 各自唯一。命名作用域要依來源案例確認。Transition 的 guard、trigger 和 effect 為原文資料，由轉換器帶入並保留順序、空白與字元。狀態的 `entry`、`exit`、`do`、`defer`、`invariant` 同樣保留來源和所屬狀態。幾何和標籤位置由下游處理。

## 建議實作順序

| 階段 | 可驗證的預期結果 | 降階前需取得的證據 |
| --- | --- | --- |
| 1. Interaction、`.`、`strict`、`◉` | 將已確認的線性序列接成有方向的轉移。序列中的 interaction 依來源順序出現，各邊保留原始 trigger、guard、effect。用課程的 `i1 . i2 . ◉` 當最小測試案例。 | 對應的 interaction 定義與最小期望圖。確認 Region 的入口、`◉` 的完成範圍，以及一個 interaction 何時對應複數事件。 |
| 2. `alt` 和 guard | 已辨認的分支從正確作用域出發，保留各分支、guard 和順序。`tests/model/cases/guarded-branch.smd.json` 手寫展示同一普通狀態上的同觸發分支，顯式 `pseudo(choice: …)` 另做案例。 | 帶兩個條件的首個 `alt` 分隔如何與三個以上運算元對應。能否使用 Choice 或 Junction 取決於該分支的語意。 |
| 3. 名稱和狀態屬性 | 同一來源節點的 Entry、Exit、Do、Deferred Events 和 Invariant 留在正確階層。引號、括號及原文範圍由來源解析器決定。 | 區分純分組、State 與 Region 的規則。確認 `entry/exit/do` 冒號兩側的結構和重複屬性處理。 |
| 4. Composite、Regions 和 `par` | 明確辨認出的 Region 以直接父子關係保存。雙層正交例的每一層有各自的 Region、節點和轉移。純 `par` 的並行和分支完成須有獨立案例。 | 提供有、無顯式 Region 的對照案例，確認並行、正交與同步的界線以及跨區轉移的擁有者。 |
| 5. 顯式 Pseudostates | `initial`、`choice`、`junction`、`fork`、`join`、`terminate` 對應同名的草案種類。 `shallowH`、`deepH`、`entryP`、`exitP` 分別對應 `shallowHistory`、`deepHistory`、`entryPoint`、`exitPoint`。Final 以 `kind: "final"` 表達。 | 用教材案例確認每種偽狀態的所屬 Region、分支、預設路徑及邊界。區分 `pseudo(fork/join...)` 與獨立語法 `fork(...)`、`join[cond]`。 |
| 6. `seq`、`>>`、`ref`、`loop` 與續接 | `iss … strict s` 的嚴格接續保留 `iss` 內部的弱順序。 `>>` 以完整程序為運算元。引用、迴圈的界限及 guard、四個符號 `0`、`◉`、`C`、`©` 都要維持各自的意義。 | 取得發送和接收的順序約束、引用作用域與遞迴規則、迴圈上下限和退出條件、四個符號單獨出現及作為 `>>` 左運算元的對照。 |

進階語法中，`raise`、AD／SD 專用構造及無法表達的行為要保留來源位置並回報。完整支援範圍以逐項可執行證據為準。

## Adapter 邊界提案

建議由 Adapter 驗證 Converter 版本及資料完整度，再提供等價的結構化來源給 Semantic Transformation。此階段先確認 Adapter 可取得的資訊，輸出格式、方法名稱、型別和錯誤代碼待外部樣本及三方同意後定案。

| 必須可取得的資訊 | 語意用途 |
| --- | --- |
| 一個或多個程序的識別、主程序、引用名稱及原始位置 | 正確解析 `ref`，對缺漏與有意的遞迴分別處理。 |
| 修訂版文法節點種類、運算元順序、分組、屬性及其明確歸屬 | 區分普通分支、顯式偽狀態、具名區域與併行構造，保留多層階層。 |
| 四種終止或續接 token、分支條件及完整的 interaction 定義 | 保留 `seq`、`>>`、分支和完成語意。原始 trigger、guard、effect 與 interaction 參照分欄保留。 |
| 原始文字或穩定的來源位置、來源的診斷和資料完整度 | 診斷可指出出問題的程序、運算子及文字範圍。若來源只有平坦 ITG，需有足以回溯名稱、階層與屬性的對應資料。 |

目前找到名稱和任務相符的公開 Converter 候選。在提交 `4c9227b`，已查到 TypeScript 的 `Diagnostic`、`SourceSpan`、`AnalysisResult` 和 `ConversionResult`。其中 `ConversionResult.output` 是 `string | null`，公開檔案尚未提供可接的 AST 或解析器。以這些檔案作為詢問版本與機器可讀匯出的依據，組別與正式介面仍待確認。[候選版 README](https://github.com/noobist-saiko/process-algebra-converter/blob/4c9227b993df5986f4f0104f7fa73ce9cd2f86dc/README.md) · [結果型別](https://github.com/noobist-saiko/process-algebra-converter/blob/4c9227b993df5986f4f0104f7fa73ce9cd2f86dc/src/application/result-types.ts)

原始 GIT 有比草案 JSON 更多的資料，例如 caller、callee、call／return、operation 與 I/O。在後續 Adapter 與轉換階段要保有原始資料或可解析的來源參照。現有 JSON 的 `sourceInteractionId` 是追溯線索，能否由下游查詢完整資料需要另行確認。若需新增對外欄位，備妥資料缺口和例子後走共同 Schema 討論。

## 建構、驗證與序列化計畫

1. 依來源宣告與出現順序走訪，先建立區域及頂點，再解析轉移端點。對來源提供的明確 ID 及自動建立的 ID 都使用同一個全域唯一性檢查。內部 ID 生成策略應可重現，且不依賴顯示名稱、隨機值或時間。
2. 逐層保存 region 的從屬、頂點類型、來源欄位與原始清單順序。來源明確且語意已有案例時才建立推導節點或轉移。轉換中保留可用的來源定位，供重複 ID、無效參照、未支援構造及語意未決診斷使用。
3. 驗證分為 JSON Schema 形狀、圖結構及已確認的語意條件。`id` 重複與端點未指向頂點屬圖結構問題。區域跨越、偽狀態的出入度及完成規則由各語意案例決定。
4. 成功時序列化已驗證的 Model，省略來源缺少的選填欄位，保持陣列順序和原始字串。遇到無法保留行為或階層的情況，回報構造與位置，阻止該結果成為可交付給下游的成功模型。

開工條件是三位成員透過 `groupctl` 確認共同目標、語言及架構、模組介面、Schema、Git 分工和驗收。取得確認後先交付 Model 的建構、驗證與序列化；第一個轉換 PR 只做有證據支撐的最小線性圖，再按上表擴充。
