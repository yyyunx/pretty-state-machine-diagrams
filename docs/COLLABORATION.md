# Group F 協作流程

GitHub 保存程式版本和 PR。上週的 [Client-side Collaboration Program](https://github.com/yyyunx/groupctl-ai-collaboration) 負責同一個 repository 的任務、介面確認、問題、審查與整合證據。

## 加入 Group F

在 README 的 Python 虛擬環境中安裝課程使用的 `groupctl`，讓工具的隔離測試能用同一套測試依賴。下列指令從專案根目錄執行。

```powershell
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install "https://github.com/yyyunx/groupctl-ai-collaboration/releases/download/v0.3.3/groupctl-0.3.3-py3-none-any.whl"
& $python -m groupctl --version
& $python -m groupctl doctor
```

確認 GitHub 的邀請已接受並可推送。首次加入的成員請用自己的 GitHub 帳號作為唯一 ID。下列 `YOUR_GITHUB_LOGIN` 替換為自己的帳號。

```powershell
$member = "YOUR_GITHUB_LOGIN"
& $python -m groupctl join --person $member --topic coordination
& $python -m groupctl context --format markdown
& $python -m groupctl inbox
```

專案初始化者或換電腦的既有成員，用 `join --resume --person $member --topic coordination` 取回既有身分。Linux 或 macOS 用 `.venv/bin/python` 執行相同的模組和子指令。

## 開發前確認

在 `people/<your-id>/coordination` 的乾淨工作目錄，由各自 AI 讀取收件匣並和自己的組員核對。初始任務分派見 README。各成員對同一個 groupctl 問題回覆自己的分工，以及對需求、語言與架構、各模組輸入輸出、兩份 JSON Schema、Git 分工與測試驗收的意見。待查證的事項保留為問題。

```powershell
# 把 QUESTION_ID 換成 inbox 顯示的問題 ID，文字換成自己的確認結果
& $python -m groupctl answer QUESTION_ID --text "我的分工及對共同草案的確認結果"
& $python -m groupctl sync
```

當三位成員的回覆齊全，再以與原問題關聯的 `finding` 記錄決定、同意成員、Schema 版本和其餘待辦。共用介面 PR 要連回協作事件。遇到語意或整合問題時，以 `groupctl ask --text "..."` 或 `groupctl block --summary "..." --action "..."` 留存紀錄。

## 開發分支與 Pull Request

`groupctl` v0.3.3 指定 `people/<person>/<topic>` 發布事件，Group F 指定 `feature/*` 開發。初始作法是在同一 repository 用 people 分支處理協作紀錄，用 feature 分支提交模組程式。可來回切換，先整理工作樹。保留 people 分支供其他成員讀取事件。

1. `git switch feature/semantic-model`、`git switch feature/layout-engine` 或 `git switch feature/renderer`。只使用自己的分支與責任目錄。
2. 修改前檢查 `git status`，使用共用 Mock 開發與測試。提交前執行 `python -m unittest discover -s tests -v`，請用裝好測試依賴的環境。
3. Commit 和 Push 自己的分支。在 GitHub 從該分支開到 `main` 的 PR，列明變更範圍、測試命令與結果、實際 commit、Mock 版本及相關 `groupctl` 事件。由至少一位其他組員審查後從 PR 合併。
4. 變更共用 Schema 或 Mock 時，在開始修改前取得三位成員共識。PR 同時附更新後的契約、Mock、測試與下游影響。
5. 將 PR 連結、測試或阻塞情況透過 `groupctl` 記錄。PR 合併後切回自己的協作分支，同步正式分支並發布整合測試證據。

```powershell
git switch "people/$member/coordination"
& $python -m groupctl sync --update
& $python -m groupctl test main
& $python -m groupctl inbox
```

`python -m unittest ...` 可測開發分支的工作樹。 `groupctl test main` 對合併後的正式 commit 以隔離工作樹重跑，並發布測試事件。預設 `main` 禁止成員直接推送日常變更。
