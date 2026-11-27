# 0.2.0 Experimental 發行草稿

- Advanced 排版提供 Fast、Balanced、Quality，原始與 Phase 3 排版均可重跑。
- 含 Python wheel、CLI、SDK、本機 Web App、靜態成果展示及完整評估。
- SMD 與 Layout 使用 0.1.0-draft JSON 契約。原始 Process Algebra 待正式 Converter。
- GitHub Actions 的發行檢查在三個作業系統建置、安裝和試跑 wheel。PyPI 及正式公開發行留待共同作者授權。

本機重建可使用 Python 3.10 以上併執行：

~~~sh
python -m pip wheel --no-deps --wheel-dir dist .
python -m pip install dist/pretty_smd-0.2.0-py3-none-any.whl
pretty-smd generate examples/basic.smd.json --algorithm advanced --mode fast --output smoke.svg
~~~

執行環境沿用 jsonschema，瀏覽器測試另用 Playwright，Graphviz 為外部比較工具。第三方授權依各套件與官方專案條款。倉庫提供安裝及課程審查構建，專案的原始碼授權由共同作者另議。
