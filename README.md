# event-maestro

**Pixel Notes（像素筆記）**：一個 2D 像素風的知識分享網站，讀者的每個互動都會被記錄成 **GA4 BigQuery export 格式**的事件，給後面的 data pipeline（[data-symphony](https://github.com/HommerChiu/data-symphony)）練習用。

資料有兩個來源，格式完全一樣：

1. **真人操作網站**：自己打開網站點來點去，事件即時寫進檔案。
2. **合成資料產生器**：一次產生幾十天、上千位讀者的歷史資料，或持續產生即時流量。

只需要 Python 3.10+，不用安裝任何套件。

## 快速開始

```bash
# 1. 啟動網站（http://127.0.0.1:8000）
python -m event_maestro serve

# 2. 產生 30 天、500 位新讀者的歷史資料（預設到昨天）
python -m event_maestro generate --users 500 --days 30

# 3. 持續產生即時流量（每分鐘約 20 個 session，Ctrl+C 停止）
python -m event_maestro stream --rate 20
```

事件會落在：

```
data/raw/ga4_events/event_date=2026-09-25/collector.jsonl
data/raw/ga4_events/event_date=2026-09-25/generator-42-20260925-30d.jsonl
data/raw/ga4_events/event_date=2026-09-26/stream-20260926143000.jsonl
```

用 DuckDB 看一下：

```sql
SELECT event_name, count(*)
FROM read_json_auto('data/raw/ga4_events/*/*.jsonl', hive_partitioning = true)
GROUP BY 1 ORDER BY 2 DESC;
```

## 網站

- 首頁、主題頁、文章頁、搜尋、收藏、登入 / 註冊、電子報訂閱。
- 文章頁可以按讚、收藏、分享、複製程式碼、下載附件、點外部連結、留言。
- 右下角 **🕹 事件面板** 會即時顯示送出的事件、目前的 `user_pseudo_id` / `ga_session_id`，也可以一鍵模擬「從 Google 搜尋 / 電子報 / Facebook / 廣告」進站。
- 在網址加上 `?utm_source=...&utm_medium=...&utm_campaign=...` 也能模擬行銷活動流量。

追蹤碼 [`web/tracker.js`](web/tracker.js) 是一個迷你版 gtag.js：自動處理 client id、30 分鐘 session、互動時間、捲動、外部連結、檔案下載，批次送到 `/collect`。

## 產生器參數

| 參數 | 預設 | 說明 |
| --- | --- | --- |
| `--users` | 500 | 這段期間的新讀者數（回訪讀者會自動產生） |
| `--days` | 30 | 期間長度 |
| `--end-date` | 昨天 | 最後一天 `YYYY-MM-DD` |
| `--seed` | 42 | 同樣的 seed 會產生完全一樣的資料 |
| `--duplicate-rate` | 0 | 故意重複寫入的比例，用來練習去重，例如 `0.01` |

讀者有三種性格（skimmer / reader / fan），閱讀深度、回訪率、互動率都不同；來源、裝置、地區、時段都有權重，所以漏斗、留存、歸因分析都會有東西可看。

## 文件

- [資料契約](docs/data-contract.md)：檔案位置、欄位、時區、和真實 GA4 的差異
- [事件字典](docs/events.md)：每個事件與參數的意義，以及可以練習的分析題目
- [JSON Schema](schema/ga4_event.schema.json)

## 設定

| 環境變數 | 預設 | 說明 |
| --- | --- | --- |
| `EVENT_MAESTRO_OUTPUT_DIR` | `data` | 輸出根目錄（也可以用 `-o`） |
| `EVENT_MAESTRO_TIMEZONE` | `Asia/Taipei` | 切 `event_date` 用的 property 時區 |

## 開發

```bash
python -m unittest discover -s tests -t . -v
```

```
event_maestro/
  ga4.py         # 組出 GA4 export 格式的一列
  collector.py   # 把 tracker.js 送來的批次轉成 GA4 列
  enrich.py      # User-Agent → device、visitor → geo
  sink.py        # 寫入 Hive 分區的 JSONL
  simulator.py   # 合成讀者（批次 / 串流）
  content.py     # 文章、作者、主題
  server.py      # 網站 + /collect
web/             # 像素風前端（index.html、app.js、tracker.js、style.css）
schema/          # JSON Schema
docs/            # 資料契約、事件字典
```
