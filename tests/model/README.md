# Semantic Model 測試計畫

這裡的可執行測試使用既有 `unittest`、JSON Schema 驗證器和共用 Mock。另有一份模組內手寫的 guarded branching JSON，作為可表達性測試。它表示一個已經選定圖形結構的例子，`alt` 對這份模型的轉換規則仍待確認。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/model -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 現階段可執行

- 用目前的 SMD Schema 驗證模組內的 guard 分支 Mock，確認同一來源和 trigger 的兩條邊各自保有 guard、effect 與 interaction ID。
- 核對不同 Region 的同名狀態可用各自的 ID 識別，以及匿名狀態維持省略 `displayName`。
- 用現有雙層正交 Mock 確認命名與未命名 Region 的歸屬，以及五項狀態資訊落在正確節點。
- 檢查十種偽狀態的 JSON 表達能力，以及 Final／Terminate 的種類區分。出入度和可執行行為在下階段驗證。

## 後續核心驗收

| 案例 | 要驗證的斷言 |
| --- | --- |
| 線性序列、嚴格接續及 Final | 遍歷可觀察 interaction 次序。用 `basic.smd.json` 作為圖形資料形狀參考，另外準備對應的來源與期望圖。無法解讀完成範圍時回報診斷。 |
| `alt` 與顯式 Choice 或 Junction | 對照普通狀態的多出邊與顯式偽狀態兩組期望圖。維持分支次序、觸發、guard、effect 和 interaction 原文。用具兩個條件、三個運算元的例子固定已確認的對應。 |
| 具名及匿名元素 | 同名或未命名頂點、區域都有各自的 ID。只有來源明確給名才存在 `displayName`。用含非 ASCII 字元與原始空白的資料核對 JSON round trip。 |
| 多層 Composite、正交 Region 與純 `par` | 核對 `nested-orthogonal.smd.json` 的直接容器關係和每區自己的頂點及轉移，另以純 `par` 及同步例子確認行為上的差異。 |
| 行為及 transition 原文 | 以 `basic` 和 `nested-orthogonal` 為格式參考。對比序列化前後欄位，逐字比對 trigger、guard、effect、來源 ID，以及 `entry`、`exit`、`do`、`defer`、`invariant` 和其作用域。 |
| 各種 Pseudostate | 顯式 Initial、Choice、Junction、Fork、Join、Shallow/Deep History、Entry/Exit Point、Terminate 分別對照已確認的圖形及行為。針對 history 的預設路徑、fork/join 的同步另外加案例。 |
| 重複 ID、無效或跨層參照、未支援和資料不完整 | 驗證重複 ID 可指出重複位置；端點若指向不存在的 ID 或非頂點 ID，定位到轉移欄位。合法跨層參照用核准的所有權案例測試。未支援構造記錄位置及構造名稱，避免交付看似成功的模型。 |
| 弱順序、引用、迴圈及續接 | 核對弱順序允許和排除的 trace。用有界迴圈、未解析引用、合法遞迴及各續接 token 在 `>>` 內外的案例測試互動次序和診斷。 |
| 相容性與可重現性 | 每份成功模型都通過現有 Schema 和結構驗證。以同一來源重複建構，核對模型物件、ID、原始內容與陣列順序。若序列化格式承諾穩定，另外逐位元比較 JSON。 |

正式輸入尚待 Converter 與組內確認。待確認後，可用 Adapter 替身餵入最小模型和雙層巢狀模型，並以已核准的真實輸出檔驗證介接。既有 12 項基礎測試維持原狀。
