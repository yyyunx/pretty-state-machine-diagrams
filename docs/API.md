# Python API 與介面相容性

~~~python
from pretty_smd import LayoutOptions, generate, load_json, prepare_model
from src.model import ModelError

document = load_json('{"kind":"unresolved","operator":"seq","sourceText":"i1 seq i2 . ◉"}')
try:
    result = generate(document, input_format="mock", options=LayoutOptions())
except ModelError as error:
    for item in error.diagnostics:
        print(item.severity, item.code, item.path, item.message)
~~~

- `load_json(text_or_bytes)` 解析 UTF-8 JSON。拒絕重複鍵、非有限數值及超出尺寸、深度或資料量限制的內容。
- `prepare_model(document, *, input_format="auto", case=None, adapter=None, uml=True)` 回傳建構好的 Model 和 UML 警告。
- `generate(document, *, input_format="auto", case=None, adapter=None, options=None, algorithm="topology", uml=True)` 回傳 `GenerationResult`，包含 `model`、`layout`、`svg`、`quality`、`warnings`。既有 `src.model`、`src.layout`、`src.renderer` 入口仍可使用。
- Adapter 自有診斷可用 `ModelError` 附上 `Diagnostic`。JSON、輸入限制及未注入 Adapter 的 `pa` 模式會拋出 `InputError`。路由無解會拋出帶轉移 ID 的 `LayoutError`。
- `LayoutOptions` 預設水平，接受 vertical，亦接受 `node_spacing=48`、`layer_spacing=64`、`region_padding=24`、`edge_clearance=8`、`crossing_penalty=85`、`bend_penalty=22`、`label_clearance=8` 的個別調整。Legacy 使用原有預設放置與路由。

## Converter Adapter

介面為 `adapt(source) -> Model`。由呼叫端建立 Adapter，使用 `generate(source, input_format="pa", adapter=adapter)` 注入。Adapter 擁有來源格式解析、Grammar 版本驗證及已解析語意的契約，Python 管線會再建構並驗證模型。至少需傳遞：

- 穩定的符號鍵與原始名稱、有序 Region／State 階層、偽狀態種類、正交關係。
- 有序轉移及其 owner、來源與目標鍵，包含跨層、回邊及解析後引用。
- 原始 Trigger、Guard、Effect、行為、互動 ID 或文字。對未解析結構提供構造種類、來源位置及診斷。

詳見 [交接提問單](../src/model/CONVERTER_HANDOFF.md)。在沒有經確認的外部版本前，`alt`、`par`、`seq`、`ref`、`loop`、`>>`、`0`、`◉`、`C`、`©` 保持未決診斷。Mock 的 resolved 控制流用於測試已明確提供的節點與轉移。

## 0.1.0-draft

兩份 Schema 均沿用。Layout 的 `nodes[id].bounds` 仍是圖元對應的方框，`edges[id].points` 是依原始方向排列的折線點。Topology 排版的端點可以落在圓、圓角、菱形或橫桿的輪廓之上，因而位於對應方框內。Entry／Exit Point 方框可跨在 Composite 邊界上。排版設定、效能及品質資料在輸出之外獨立傳遞。
