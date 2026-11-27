# 共用 JSON 介面草案

Schema 採 JSON Schema Draft 2020-12。資料使用 UTF-8，版本欄位為 `0.1.0-draft`。這份契約可用來開發 Mock 和測試，仍需三位成員確認。

## SMD Model

- 頂層 `regions` 及 Composite State 的 `regions` 皆保留直接隸屬與順序。每個 Region 儲存其 `vertices` 與其擁有的 `transitions`。同一 Composite 的多個直接 Region 可表達正交區域。
- `vertex.kind` 為 `state`、`composite`、`pseudostate` 或 `final`。初始頂點使用 `kind: "pseudostate"` 與 `pseudostateKind: "initial"`。
- `id` 對每份 Model 全域唯一，涵蓋機器、區域、節點及轉移。它是內部識別值。明確命名才帶 `displayName`，未命名時省略欄位，渲染時保持空白。
- State 和 Composite 的選填 `behaviors` 可保留 `entry`、`exit`、`do`、`defer` 的原文陣列及 `invariant` 原文。
- 轉移的 `sourceId` 與 `targetId` 引用同一份 Model 的 vertex。選填 `triggers`、`guard`、`effect` 保存原文。若來源提供整段標記或 interaction 參照，可填 `sourceText` 或 `sourceInteractionId`。無 trigger 的完成轉移可省略 `triggers`。跨層轉移的所有權和 UML 限制要以 Converter 和老師案例確認。

## Layout Data

- `modelId` 等於 Model 的 `id`。 `nodes`、`regions`、`edges` 以 SMD 的內部 ID 為索引，分別對應 vertex、region 和 transition，包含所有層級的項目。
- `viewport`、`bounds`、`labelBounds` 使用同一個絕對座標系，原點在左上，X 向右、Y 向下。尺寸為正數。Region 的框是幾何範圍，可作為裁切和排版依據。
- 轉移的 `points` 從 source 到 target 排列，至少有起終點。`labelBounds` 為選填文字範圍。所有顯示文字由 Model 取得。
- Region 的 `separatorSegments` 是用於虛線的起終點對。已命名的 Composite State 標籤在容器上方，Region 標籤保留在分隔線處，分段留空給文字，無名稱時保持空白。雙層 Mock 以後一列 Region 持有上方分隔線為例。首區有名稱、相鄰區域同時有名稱或直排時的歸屬與位置仍待確認。

## 交接與驗證

| 模組 | 輸入 | 輸出 |
| --- | --- | --- |
| Semantic Model | 待確認的 Converter 輸出 | [SMD Model JSON](../schemas/smd-model.schema.json) |
| Layout Engine | SMD Model JSON | [Layout Data JSON](../schemas/layout.schema.json) |
| Renderer | 同一份 SMD Model JSON 與 Layout Data JSON | UML 圖形，輸出格式待確認 |

先做 Schema 驗證，再做跨檔驗證。 `tests/integration/test_contracts.py` 檢查全域唯一 ID、轉移端點和 Layout 索引覆蓋，並測試兩組共用 Mock。正式語意、視覺驗收和 API 簽章留待後續 PR 確認。
