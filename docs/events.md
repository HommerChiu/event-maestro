# 事件字典（Event dictionary）

每個事件都會帶下面這些「共同參數」，其餘參數依事件而定。參數都放在 `event_params`（GA4 的 key / value 陣列）。

| 共同參數 | 型別 | 說明 |
| --- | --- | --- |
| `ga_session_id` | int | session 開始時間（epoch 秒）。`user_pseudo_id` + `ga_session_id` 才是唯一的 session key |
| `ga_session_number` | int | 這位讀者的第幾次 session |
| `page_location` | string | 事件發生時的完整網址 |
| `page_title` | string | 頁面標題 |
| `engaged_session_event` | int | 1 = session 已達「互動」條件（停留 ≥ 10 秒或 ≥ 2 個 page_view） |
| `session_engaged` | string | `"1"`，只在 session 已互動時出現（與 GA4 相同） |

文章相關事件另外會帶「文章參數」：

| 文章參數 | 型別 | 說明 |
| --- | --- | --- |
| `article_id` | string | 例如 `a001` |
| `article_title` | string | 文章標題 |
| `author` | string | 作者名稱 |
| `topic` | string | 主題代碼：`lakehouse`、`modeling`、`streaming`、`orchestration`、`analytics`、`quality` |
| `content_group` | string | 主題中文名稱（非文章頁則是 `home`、`search`、`topic`、`account`…） |
| `word_count` | int | 字數（估算） |
| `reading_time_min` | int | 預估閱讀分鐘數 |

## 自動收集（對應 GA4 enhanced measurement）

| 事件 | 何時觸發 | 專屬參數 |
| --- | --- | --- |
| `first_visit` | 這個瀏覽器第一次來 | — |
| `session_start` | 新 session（第一次來，或閒置超過 30 分鐘） | — |
| `page_view` | 每次換頁（SPA 路由變化也算） | `page_referrer`，文章頁另帶文章參數 |
| `user_engagement` | 離開頁面或切到背景時 | `engagement_time_msec` |
| `scroll` | 頁面捲到 90% | `percent_scrolled` = 90 |
| `click` | 點擊外部連結 | `link_url`、`link_domain`、`link_text`、`outbound` |
| `file_download` | 點擊下載檔案 | `file_name`、`file_extension`、`link_url`、`link_text` |
| `view_search_results` | 進入帶有 `?q=` 的搜尋頁 | `search_term`、`search_results` |

## 網站自訂事件

| 事件 | 何時觸發 | 專屬參數 |
| --- | --- | --- |
| `search` | 送出搜尋框 | `search_term` |
| `select_content` | 從列表點進文章 | `content_type` = `article`、`content_id`、`item_list_name`（`latest`、`topic_*`、`search_results`、`related_articles`、`bookmarks`）+ 文章參數 |
| `read_progress` | 文章讀到 25 / 50 / 75 / 100% | `percent_read`、`seconds_on_page` + 文章參數 |
| `like_article` / `unlike_article` | 按讚 / 取消 | 文章參數 |
| `bookmark_article` / `remove_bookmark` | 收藏 / 取消收藏 | 文章參數 |
| `share` | 分享按鈕 | `method`（`copy_link`、`x`、`facebook`）、`content_type`、`item_id` + 文章參數 |
| `copy_code` | 複製文章中的程式碼 | `code_lines` + 文章參數 |
| `submit_comment` | 送出留言 | `comment_length`、`logged_in` + 文章參數 |
| `subscribe_newsletter` | 訂閱電子報 | `newsletter`、`already_subscribed`、`form_location` |
| `sign_up` | 註冊 | `method`（`email`、`github`） |
| `login` | 登入 | `method` |

> 合成資料產生器不會產生 `unlike_article` 和 `remove_bookmark`，這兩個只會出現在真人操作網站的資料裡。

## user 層級欄位

- `user_pseudo_id`：瀏覽器的 client id（`隨機數.首次造訪秒數`），等同 GA4 的 `_ga` cookie。
- `user_id`：登入或註冊後才有，格式 `reader-xxxxxx`。可以用來練習把同一個人在不同裝置的 `user_pseudo_id` 串起來。
- `user_properties`：`newsletter_subscriber` = `yes`、`signed_up` = `yes`。
- `traffic_source`：讀者**第一次**進站的來源（首次接觸歸因）。
- `collected_traffic_source`：**這一次** session 帶進來的 UTM，只出現在 session 開頭的 `first_visit` / `session_start` / 第一個 `page_view`。

## 值得拿來練習的分析

- **Sessionization**：用 `user_pseudo_id` + `ga_session_id` 組 session 表，算跳出率、平均互動時間、到達頁。
- **閱讀漏斗**：`page_view` → `select_content` → `read_progress` 50 → 100 → `subscribe_newsletter`。
- **內容表現**：每篇文章的完讀率、按讚率、分享率，依 `topic` 比較。
- **Cohort 留存**：用 `user_first_touch_timestamp` 分群。
- **歸因**：比較 `traffic_source`（首次）與 `collected_traffic_source`（當次）。
- **身分合併**：同一個 `user_id` 對應多個 `user_pseudo_id`。
- **資料品質**：用 `--duplicate-rate` 產生重複事件，練習去重。
