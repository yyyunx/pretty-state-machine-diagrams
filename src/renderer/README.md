# Renderer & Integration

由 `feature/renderer` 負責。Renderer 接收同一份 SMD Model JSON 與 Layout Data JSON，輸出獨立 SVG。Renderer 不重新解讀 Process Algebra：顯示名稱、behaviors、transition 原文只讀取 Model；所有座標與路徑只讀取 Layout。

## Python API

```python
from src.renderer import render, render_files

svg = render(model_dict, layout_dict)
render_files(
    "examples/basic.smd.json",
    "examples/basic.layout.json",
    "out/state-machine.svg",
)
```

## CLI

```bash
python -m src.renderer examples/basic.smd.json examples/basic.layout.json out/basic.svg
```

## Browser demo

直接開啟 `demo/index.html`，編輯 SMD Model 與 Layout JSON，按 **Render SVG** 預覽，或按 **Download SVG** 匯出。Demo 的 JavaScript renderer 是方便展示的輕量實作；正式 Python Renderer 是整合 API。

## Validation and tests

Renderer 檢查 model/layout 版本與 modelId、全域唯一 Model ID、transition 端點、Layout 對每個 vertex/region/transition 的完整覆蓋、座標與路徑點。缺漏或不一致時丟出 `RenderError`，不輸出部分圖形。

```bash
python -m unittest tests.renderer.test_renderer tests.integration.test_renderer_end_to_end -v
python -m unittest discover -s tests -v
```

## Display rules

- 只有 Model 明確提供 `displayName` 才顯示 State / Composite / Region 名稱；不顯示內部 ID。
- Composite 與 Region 以 Model 的巢狀關係遞迴繪製。
- Region 分隔線只使用 Layout 的 `separatorSegments`；有名稱時以白底標籤留空。
- Transition 標籤優先保留 `sourceText`；否則由 trigger、guard、effect 組合顯示。
- entry、do、exit、defer、invariant 依原始 Model 資料呈現在 State compartment。
