# 共同架構草案

```text
Process Algebra + interaction definitions
    → R/S Converter export (input contract pending)
    → Semantic Model      → SMD Model JSON
    → Layout Engine       → Layout Data JSON
    → Renderer            ← SMD Model JSON + Layout Data JSON
```

Semantic Model 擁有階層、狀態、轉移和行為。Layout Engine 以唯讀 Model 計算幾何資料。Renderer 依同一份 Model 選擇圖形與標籤，再按 Layout 放置元素。應用程式語言、CLI 或函式介面、如何載入元件、排版方式及 SVG 等輸出選項待共同決策。Python 3.10+ 與 `unittest` 提供這次的共用驗證。

## Converter 確認項目

老師將 Process Algebra Converter 分派給 R、S 組。接手可用的輸出之前，Semantic Model 負責與兩組確認下列資料及實際樣本。

1. 取得可用的 repository、版本、執行方式、輸入文件及輸出格式。
2. 查核 AST、語意圖或等價資料能否保留巢狀分組、屬性作用域、具名和匿名元素、區域、引用和偽狀態。
3. 驗證 interaction 定義、原始 token、弱順序的事件資訊、guard 和 effect、缺漏或不支援語法的診斷。若輸出是平坦 ITG，確認有可對回階層的資料。
4. 用一個最小範例和一個雙層正交範例確認可重用路徑，再決定最薄的 adapter。若資料缺失，先透過 `groupctl` 回報，以老師的說明釐清後再決定補法。

## 階段計畫

1. 三位成員確認 [介面](INTERFACE.md)、Mock、共用測試和區域分隔標籤規則，透過 `groupctl` 記錄決策。
2. 各模組在自有分支依約定格式實作，並從簡單及巢狀案例各跑一次自有測試。
3. 以 PR 合併；用實際 Converter 資料串接三個模組，檢查原始語意、圖元及視覺可讀性，發布整合測試證據。
