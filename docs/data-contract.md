# 資料契約（Data contract）

給下游 pipeline（例如 `data-symphony`）看的：event-maestro 產出什麼、放在哪裡、長什麼樣子。

## 放在哪裡

```
<output>/raw/ga4_events/event_date=YYYY-MM-DD/<source>.jsonl
```

| 部分 | 說明 |
| --- | --- |
| `<output>` | 預設 `./data`，可用環境變數 `EVENT_MAESTRO_OUTPUT_DIR` 或 `-o` 參數改 |
| `event_date=YYYY-MM-DD` | Hive 風格分區，ISO 日期，Spark / DuckDB / Trino 會自動解析成 DATE |
| `<source>.jsonl` | `collector.jsonl`（真人操作網站）、`generator-<seed>-<end>-<days>d.jsonl`（批次產生）、`stream-<啟動時間>.jsonl`（串流產生） |

- 同一個分區可能同時有好幾個來源的檔案，下游直接讀整個資料夾即可。
- `generate` 用同樣參數重跑會**覆蓋**自己的檔案，不會重複附加；`collector` 和 `stream` 是持續 append。
- 事件依 **property 時區**（預設 `Asia/Taipei`，可用 `EVENT_MAESTRO_TIMEZONE` 改）切日期，跟 GA4 一樣。所以 UTC 的 16:00 之後就屬於隔天的分區。
- 分區欄位和列裡的欄位同名：用 `hive_partitioning` 讀時，`event_date` 會變成分區的 DATE（`2026-09-25`），而不是列裡的字串 `20260925`，兩者代表同一天。
- 一個 session 跨過午夜時，後面的事件會落到隔天的分區（GA4 也是這樣）。

## 格式

- UTF-8、newline-delimited JSON，一行一個事件。
- 欄位名稱與型別**完全比照 GA4 BigQuery export**（`events_YYYYMMDD` 表），所以網路上 GA4 的 SQL 範例幾乎都能直接套用。
- 所有欄位都一定會出現，沒有值就是 `null`，方便 schema 推斷。
- 正式 schema：[`schema/ga4_event.schema.json`](../schema/ga4_event.schema.json)（JSON Schema 2020-12）。

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `event_date` | STRING | `YYYYMMDD`，property 時區 |
| `event_timestamp` | INT64 | 客戶端事件時間，UTC 微秒 |
| `event_name` | STRING | 見 [事件字典](events.md) |
| `event_params` | ARRAY<STRUCT<key STRING, value STRUCT<string_value, int_value, float_value, double_value>>> | 事件參數 |
| `event_previous_timestamp` | INT64 | 同一位讀者上一個事件的時間 |
| `event_value_in_usd` | FLOAT64 | 永遠是 null（知識網站沒有營收） |
| `event_bundle_sequence_id` | INT64 | 同一批送出的事件共用 |
| `event_server_timestamp_offset` | INT64 | 伺服器收到時間 − 客戶端時間（微秒） |
| `user_id` | STRING | 登入後才有 |
| `user_pseudo_id` | STRING | 瀏覽器 client id |
| `privacy_info` | STRUCT | 固定為同意 |
| `user_properties` | ARRAY<STRUCT<key, value STRUCT<…, set_timestamp_micros>>> | 讀者屬性 |
| `user_first_touch_timestamp` | INT64 | 第一次造訪時間（微秒） |
| `user_ltv` | STRUCT<revenue, currency> | 永遠 0 USD |
| `device` | STRUCT | `category`（desktop / mobile / tablet）、`operating_system`、`operating_system_version`、`language`、`mobile_brand_name`、`mobile_model_name`、`web_info.browser`、`web_info.browser_version`、`web_info.hostname` 等 |
| `geo` | STRUCT | `continent`、`sub_continent`、`country`、`region`、`city`、`metro` |
| `app_info` | STRUCT | 永遠 null（這是 web stream） |
| `traffic_source` | STRUCT<name, medium, source> | 首次進站來源 |
| `stream_id` | STRING | 固定 `1234567890` |
| `platform` | STRING | 固定 `WEB` |
| `event_dimensions` | STRUCT | 永遠 null |
| `ecommerce` | STRUCT | 欄位存在但全是 null（保留 GA4 原始 schema） |
| `items` | ARRAY | 永遠是空陣列 |
| `collected_traffic_source` | STRUCT | 當次 session 的 UTM，僅在 session 開頭事件出現 |
| `is_active_user` | BOOL | 固定 true |
| `batch_event_index` | INT64 | 在同一批內的順序 |

## 範例

取某個參數（DuckDB）：

```sql
SELECT
  event_name,
  user_pseudo_id,
  list_filter(event_params, p -> p.key = 'ga_session_id')[1].value.int_value AS ga_session_id,
  list_filter(event_params, p -> p.key = 'article_id')[1].value.string_value AS article_id
FROM read_json_auto('data/raw/ga4_events/*/*.jsonl', hive_partitioning = true)
LIMIT 10;
```

同樣的事在 BigQuery / Spark SQL 會寫成 `(SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id')`。

## 已知與真實 GA4 不同的地方

- `geo` 不是從 IP 查的，而是用 `user_pseudo_id` 雜湊後從固定的城市清單挑一個（本機跑的時候 IP 都是 127.0.0.1）。
- `device` 由一個簡易的 User-Agent 解析器產生，只涵蓋常見瀏覽器。
- 沒有 intraday 表、沒有 72 小時內的回補更新。
- 產生器的 `--duplicate-rate` 會故意寫入完全相同的重複列，用來練習去重。
