# 台股個股分析儀表板：每日自動更新版

每個交易日台灣時間 18:40 和 21:50，GitHub 會自動抓最新的日K和三大法人，寫進 `data/`，網頁打開就是最新資料。全部免費。

## 檔案

| 檔案 | 用途 |
|---|---|
| `index.html` | 儀表板本體 |
| `update.py` | 抓資料的程式（FinMind 為主，證交所備援） |
| `stocks.txt` | 要追蹤的股票代號，一行一個 |
| `data/6446.json` | 6446 的歷史資料，先放好，第一次就有圖 |
| `workflow-update.yml.txt` | 排程設定的內容，步驟 4 要貼上用 |

## 架設步驟（建議用電腦，約 15 分鐘）

1. 到 github.com 註冊帳號並登入。
2. 右上角「+」→ New repository。名稱填 `stock`，選 **Public**，按 Create repository。
3. 點頁面上的「uploading an existing file」，把 `index.html`、`update.py`、`stocks.txt` 和整個 `data` 資料夾拖進去，按 Commit changes。
4. 建立排程檔：Add file → Create new file，檔名欄位**完整貼上** `.github/workflows/update.yml`，內容貼上 `workflow-update.yml.txt` 裡的全部文字，按 Commit changes。
5. 開啟網頁：Settings → Pages → Source 選「Deploy from a branch」，Branch 選 `main`、資料夾選 `/ (root)`，按 Save。等一兩分鐘，網址是 `https://你的帳號.github.io/stock/`，加到手機主畫面即可。
6. 測試排程：Actions 分頁 → 左邊「每日更新股票資料」→ Run workflow。約一分鐘後出現綠色勾勾就成功。
   - 如果紅色叉叉且訊息有 `permission` 或 `403`：Settings → Actions → General → Workflow permissions 改成「Read and write permissions」，再跑一次。

只用手機也能做：步驟 3 改成用 Add file → Create new file 一個一個建立（檔名照上表，`data/6446.json` 要連資料夾一起打），內容用複製貼上。

## 日常使用

- **加股票**：在 GitHub 上編輯 `stocks.txt`，一行加一個代號（上市上櫃都可以），存檔後到 Actions 手動跑一次，新股票會自動抓約 400 天的歷史。
- **在網頁切換股票**：左上角輸入代號按「切換股票」。不在 `stocks.txt` 裡的代號會顯示示範資料。
- **提高額度（選用）**：到 finmindtrade.com 註冊取得 token，在 Settings → Secrets and variables → Actions 新增名為 `FINMIND_TOKEN` 的 secret。追蹤十幾檔以內不需要。

## 已知限制

- 這是盤後資料，盤中不會動。
- GitHub 排程不保證準時，可能晚幾分鐘到半小時。
- 三大法人通常傍晚前公布，所以排了兩次，第二次用來補齊。
- 除權息日之前的價格會自動還原，數字會比當時的原始報價低。
- 資料僅供自己參考，不構成投資建議。
