# Pretty State Machine Diagrams

Group F 的期末專案。目標是從課程的 Process Algebra 生成保留原始行為與階層的 UML State Machine Diagram，並改善圖的可讀性。

目前是共同基礎建設。JSON 契約採用 `0.1.0-draft`，Python 3.10+ 用於契約測試。應用程式語言、解析器介面、排版演算法和輸出格式仍由三位成員共同確認。

| 工作 | 開發分支 | 自有目錄 | 可先使用的資料 |
| --- | --- | --- | --- |
| Semantic Model | `feature/semantic-model` | `src/model/`、`tests/model/` | `examples/*.smd.json` 作為預期輸出格式 |
| Layout Engine | `feature/layout-engine` | `src/layout/`、`tests/layout/` | `examples/*.smd.json` 作為輸入 |
| Renderer & Integration | `feature/renderer` | `src/renderer/`、`tests/renderer/`、`tests/integration/` | 同名的 `*.smd.json` 和 `*.layout.json` |

## 開始協作

在各自電腦執行下列指令。最後一行依分工改成自己的開發分支。

```powershell
git clone https://github.com/yyyunx/pretty-state-machine-diagrams.git
cd pretty-state-machine-diagrams
git switch feature/semantic-model
```

先讀 [AGENTS.md](AGENTS.md)、[課程要求](docs/REQUIREMENTS.md)、[共同架構](docs/ARCHITECTURE.md)、[介面草案](docs/INTERFACE.md)及 [兩份 Schema](schemas/)。按 [協作流程](docs/COLLABORATION.md) 加入 `groupctl`、讀取收件匣並回覆共同介面提案。取得共識後，各分支以 Mock 平行開發。

## 執行測試

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Linux 或 macOS 使用 `.venv/bin/python`。測試涵蓋 Schema、Mock 物件的跨檔引用、命名與巢狀結構。兩組 [Mock](examples/) 以同名配對，分別涵蓋基本狀態轉移及雙層正交區域。
