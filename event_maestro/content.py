"""Articles shown on the knowledge-sharing site.

The same catalog drives the website (served as JSON at ``/api/articles``)
and the synthetic generator, so article ids, titles, authors and topics in
the generated data match what a real visitor would produce.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

AUTHORS = {
    "ben": {"name": "Ben", "title": "資料工程師", "avatar": "wizard"},
    "mia": {"name": "Mia", "title": "分析工程師", "avatar": "knight"},
    "leo": {"name": "Leo", "title": "平台工程師", "avatar": "robot"},
    "ivy": {"name": "Ivy", "title": "資料科學家", "avatar": "slime"},
}

TOPICS = {
    "lakehouse": "Lakehouse",
    "modeling": "資料建模",
    "streaming": "串流處理",
    "orchestration": "排程編排",
    "analytics": "產品分析",
    "quality": "資料品質",
}


@dataclass(frozen=True)
class Article:
    id: str
    title: str
    author: str
    topic: str
    tags: tuple[str, ...]
    published_at: str
    summary: str
    body: tuple[str, ...]
    code: str = ""
    links: tuple[tuple[str, str], ...] = ()
    download: str = ""
    word_count: int = field(default=0)

    @property
    def reading_time_min(self) -> int:
        return max(1, round(self.word_count / 300))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["author_name"] = AUTHORS[self.author]["name"]
        data["topic_name"] = TOPICS[self.topic]
        data["reading_time_min"] = self.reading_time_min
        data["links"] = [{"label": label, "url": url} for label, url in self.links]
        return data


def _article(**kwargs) -> Article:
    text = "".join(kwargs["body"]) + kwargs.get("code", "")
    return Article(word_count=len(text) * 3, **kwargs)


ARTICLES: tuple[Article, ...] = (
    _article(
        id="a001",
        title="Iceberg 表格格式入門：為什麼大家都在談 Lakehouse",
        author="ben",
        topic="lakehouse",
        tags=("iceberg", "lakehouse", "table-format"),
        published_at="2026-06-02",
        summary="從 Hive 表的痛點出發，看 Iceberg 如何用 metadata 層解決 schema 演進與時間旅行。",
        body=(
            "傳統的 Hive 表把分區綁在目錄結構上，一旦分區欄位要改就得整個重寫。",
            "Iceberg 把表的狀態寫成一連串 snapshot，每個 snapshot 指向 manifest list，再指向 data file。",
            "因為讀取端只看 metadata，就能做到原子性 commit、隱藏分區與時間旅行查詢。",
        ),
        code="SELECT * FROM events FOR SYSTEM_TIME AS OF '2026-06-01 00:00:00';",
        links=(("Apache Iceberg 官方文件", "https://iceberg.apache.org/docs/latest/"),),
        download="iceberg-cheatsheet.md",
    ),
    _article(
        id="a002",
        title="用 dbt 把 GA4 原始事件整理成 session 表",
        author="mia",
        topic="modeling",
        tags=("dbt", "ga4", "sessionization"),
        published_at="2026-06-10",
        summary="GA4 匯出的巢狀 event_params 要怎麼攤平？一步步做出 stg、int、mart 三層模型。",
        body=(
            "GA4 的 event_params 是 key/value 陣列，第一步通常是寫一個 macro 把常用參數取出來。",
            "session 的主鍵是 user_pseudo_id 加上 ga_session_id，這個組合在整個 property 內唯一。",
            "有了 session 表之後，跳出率、平均互動時間、到達頁都能從同一張表算出來。",
        ),
        code=(
            "select user_pseudo_id,\n"
            "  (select value.int_value from unnest(event_params) where key = 'ga_session_id') as session_id\n"
            "from {{ source('ga4', 'events') }}"
        ),
        links=(("dbt Docs", "https://docs.getdbt.com/"),),
    ),
    _article(
        id="a003",
        title="Kafka 與事件串流：從 batch 走到 real-time",
        author="leo",
        topic="streaming",
        tags=("kafka", "streaming", "cdc"),
        published_at="2026-06-18",
        summary="topic、partition、consumer group 三個概念搞懂，就能開始設計串流 pipeline。",
        body=(
            "Kafka 的 topic 是一條 append-only 的日誌，partition 決定了平行度與順序保證的範圍。",
            "consumer group 讓多個消費者分攤 partition，offset 則記錄了每個 group 讀到哪裡。",
            "把網站事件先送進 Kafka，下游就能同時接即時看板與離線倉儲。",
        ),
        code="kafka-console-consumer --topic ga4_events --from-beginning --group demo",
        links=(("Kafka Documentation", "https://kafka.apache.org/documentation/"),),
    ),
    _article(
        id="a004",
        title="Airflow vs Dagster：排程工具怎麼選",
        author="leo",
        topic="orchestration",
        tags=("airflow", "dagster", "orchestration"),
        published_at="2026-07-01",
        summary="task 導向與 asset 導向兩種思維的差異，以及各自適合的團隊規模。",
        body=(
            "Airflow 以 DAG 與 task 為中心，強項是生態系與大量現成 operator。",
            "Dagster 以 software-defined asset 為中心，天生知道每張表的上下游與新鮮度。",
            "小團隊從 asset 思維出發，通常能更快看懂整個資料平台長什麼樣子。",
        ),
        links=(
            ("Airflow", "https://airflow.apache.org/"),
            ("Dagster", "https://dagster.io/"),
        ),
    ),
    _article(
        id="a005",
        title="漏斗分析實戰：找出讀者在哪裡離開",
        author="ivy",
        topic="analytics",
        tags=("funnel", "ga4", "sql"),
        published_at="2026-07-08",
        summary="從 page_view 到 read_progress 100%，用 SQL 算出每一步的轉換率。",
        body=(
            "漏斗的每一步都要定義清楚：以使用者計還是以 session 計，是否要求依序發生。",
            "閱讀網站常見的漏斗是：進站 → 打開文章 → 讀到一半 → 讀完 → 訂閱電子報。",
            "把每一步的人數畫出來，最大的落差通常就是最值得優化的地方。",
        ),
        code=(
            "select count(distinct if(event_name = 'page_view', user_pseudo_id, null)) as step1,\n"
            "       count(distinct if(event_name = 'read_progress', user_pseudo_id, null)) as step2\n"
            "from events"
        ),
        download="funnel-template.sql",
    ),
    _article(
        id="a006",
        title="留存率 Cohort 分析：新讀者會回來嗎",
        author="ivy",
        topic="analytics",
        tags=("retention", "cohort", "sql"),
        published_at="2026-07-15",
        summary="用 user_first_touch_timestamp 分群，計算第 N 天回訪比例並畫出留存三角形。",
        body=(
            "cohort 以首次造訪日期分群，之後每一天看這群人有多少比例又出現。",
            "GA4 匯出的 user_first_touch_timestamp 正好就是分群依據，不必自己再算。",
            "留存曲線趨於平緩的位置，代表網站真正留下來的核心讀者。",
        ),
    ),
    _article(
        id="a007",
        title="資料品質第一步：用 Great Expectations 守住原始層",
        author="mia",
        topic="quality",
        tags=("data-quality", "testing"),
        published_at="2026-07-22",
        summary="重複事件、遲到資料、缺漏欄位，三種最常見的原始資料問題與檢查方法。",
        body=(
            "事件資料最常見的問題是重送造成的重複，可以用 user_pseudo_id、event_timestamp、event_name 去重。",
            "遲到資料指事件時間很早，但很晚才進到倉儲，增量模型要留一段回補窗口。",
            "在原始層就寫好期望值檢查，比在報表出錯後才追查便宜得多。",
        ),
        links=(("Great Expectations", "https://greatexpectations.io/"),),
    ),
    _article(
        id="a008",
        title="Polaris Catalog：讓多個引擎共用同一份 Iceberg 表",
        author="ben",
        topic="lakehouse",
        tags=("polaris", "iceberg", "catalog"),
        published_at="2026-08-05",
        summary="REST catalog 是 Lakehouse 的交通樞紐，Spark、Trino、DuckDB 都能透過它讀寫。",
        body=(
            "Iceberg 的 catalog 負責記錄每張表目前的 metadata 位置，commit 時做 compare-and-swap。",
            "Polaris 實作了 Iceberg REST catalog 規格，並加上權限控管。",
            "只要指向同一個 catalog，不同查詢引擎看到的就是同一個版本的表。",
        ),
        links=(("Apache Polaris", "https://polaris.apache.org/"),),
    ),
    _article(
        id="a009",
        title="維度建模複習：事實表與維度表",
        author="mia",
        topic="modeling",
        tags=("kimball", "star-schema"),
        published_at="2026-08-19",
        summary="grain、事實、維度三件事先決定，星狀模型就不會長歪。",
        body=(
            "先決定事實表的 grain，例如一列代表一次文章閱讀或一個 session。",
            "維度表描述事實發生的情境：誰（讀者）、什麼（文章）、何時（日期）。",
            "緩慢變化維度讓我們保留作者改名、文章改分類之前的歷史。",
        ),
        download="star-schema-diagram.md",
    ),
    _article(
        id="a010",
        title="DuckDB 本機分析：一行指令讀完整個資料夾的 JSON",
        author="ben",
        topic="lakehouse",
        tags=("duckdb", "json", "local"),
        published_at="2026-09-02",
        summary="不用架伺服器，DuckDB 直接讀 Hive 分區的 JSONL，最適合拿來探索事件資料。",
        body=(
            "DuckDB 的 read_json_auto 會自動推斷巢狀欄位的型別，連 event_params 陣列都能讀。",
            "搭配 hive_partitioning，路徑上的 event_date= 會自動變成一個欄位。",
            "探索完再決定要不要進 Iceberg，是很輕量的學習起點。",
        ),
        code=(
            "SELECT event_name, count(*)\n"
            "FROM read_json_auto('data/raw/ga4_events/*/*.jsonl', hive_partitioning = true)\n"
            "GROUP BY 1 ORDER BY 2 DESC;"
        ),
        links=(("DuckDB", "https://duckdb.org/docs/"),),
    ),
    _article(
        id="a011",
        title="Lightdash：把 dbt 模型直接變成 BI 看板",
        author="ivy",
        topic="analytics",
        tags=("lightdash", "bi", "dbt"),
        published_at="2026-09-12",
        summary="在 dbt 的 yml 裡定義 metric，Lightdash 就能讓大家自助拖拉分析。",
        body=(
            "Lightdash 讀取 dbt 專案的 manifest，把每個 model 變成可探索的表。",
            "metric 與 dimension 都寫在 yml 裡，跟著程式碼一起版本控制。",
            "這讓分析邏輯只有一份定義，避免各個看板算出不同的數字。",
        ),
        links=(("Lightdash", "https://www.lightdash.com/"),),
    ),
    _article(
        id="a012",
        title="Spark Structured Streaming 寫入 Iceberg",
        author="leo",
        topic="streaming",
        tags=("spark", "iceberg", "streaming"),
        published_at="2026-09-20",
        summary="micro-batch、checkpoint 與小檔案問題，串流寫入 Lakehouse 的三個關鍵。",
        body=(
            "Structured Streaming 以 micro-batch 執行，每個 batch 對 Iceberg 就是一次 commit。",
            "checkpoint 記錄了來源 offset 與 sink 狀態，重啟後能 exactly-once 接續。",
            "commit 太頻繁會產生大量小檔案，需要定期 rewrite_data_files 做 compaction。",
        ),
        code=(
            "df.writeStream.format('iceberg')\n"
            "  .option('checkpointLocation', '/tmp/ckpt')\n"
            "  .toTable('lake.web.ga4_events')"
        ),
    ),
)

ARTICLES_BY_ID = {a.id: a for a in ARTICLES}


def catalog() -> dict:
    return {
        "authors": AUTHORS,
        "topics": TOPICS,
        "articles": [a.to_dict() for a in ARTICLES],
    }


def article_params(article: Article) -> dict:
    """Event parameters attached to every article-level event."""
    return {
        "article_id": article.id,
        "article_title": article.title,
        "author": AUTHORS[article.author]["name"],
        "topic": article.topic,
        "content_group": TOPICS[article.topic],
        "word_count": article.word_count,
        "reading_time_min": article.reading_time_min,
    }
