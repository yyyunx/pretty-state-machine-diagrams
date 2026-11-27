# 課程要求與目前範圍

老師負責分派任務。D、E、F 組各自完成 Pretty State Machine Diagrams，第二輪才會評估與整合。組內三位成員及各自的 AI 必須使用課程的 Client-side Collaboration Program 共同釐清需求、分工、執行和查核。

## 課程來源

1. 老師的作業分派與 Pretty State Machine Diagrams 對話。最新提醒要求顯示名稱必須來自明確命名、Composite State 名稱在容器上方，Region 名稱落在虛線分隔處，未命名時留空，各層巢狀皆適用。
2. 對話提供的修訂版 Process Algebra Grammar。它補入狀態相關行為、區域屬性和 UML Pseudostate 等結構。語法與語意優先級高於論文的舊版 Grammar。
3. Haga、Ma、Chao 的 *SBC Process Algebra for SysML Model Inconsistency Checking*，12 頁課程草稿。第 III.B–C 節與 Fig. 3 說明舊 Grammar、guarded interaction 與 ITG。第 IV.A–B 節與 Figs. 4–7 說明弱順序的不同事件次序以及 GIT 與轉移的關係。第 V 節與 Fig. 11 的 XML 是論文工具示例。Group F 對外格式須另行確認。

見 [修訂 Grammar 與 UML 對應](GRAMMAR.md)。外部 Converter 由 R、S 組負責，交付介面、支援的修訂版本和可取得的測試輸入待確認。

## 驗收

本階段驗收兩份 Schema、兩組成對 Mock、跨檔關聯與協作流程。正式開發前由三位成員確認共同決策。正式整合時要追加老師提供的實際 Process Algebra 案例，驗證轉移語意、巢狀區域與匿名元素在成圖中一致，並確認分隔線、文字、節點和轉移路徑的可讀性。
