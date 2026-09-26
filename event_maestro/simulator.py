"""Synthetic readers for the Pixel Notes site.

The simulator walks virtual readers through the same pages the real site
has and emits the same events ``web/tracker.js`` would, then passes them
through the same :func:`ga4.build_event_row` the collector uses. Output is
deterministic for a given ``--seed``.

Two modes:

* :func:`generate_history` backfills N days of traffic (batch pipelines).
* :func:`stream` keeps producing sessions in real time (streaming pipelines).
"""

from __future__ import annotations

import heapq
import random
import time
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from typing import Iterator

from . import ga4
from .content import ARTICLES, TOPICS, Article, article_params
from .enrich import geo_for_visitor, parse_user_agent

SITE = "https://pixel-notes.local"
MICROS = 1_000_000

USER_AGENTS: tuple[tuple[str, float], ...] = (
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36", 26),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15", 12),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36", 12),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0", 4),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0", 5),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1", 20),
    ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36", 7),
    ("Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36", 8),
    ("Mozilla/5.0 (iPad; CPU OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1", 4),
    ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36", 2),
)
LANGUAGES = (("zh-tw", 65), ("en-us", 20), ("ja-jp", 6), ("zh-hk", 5), ("de-de", 2), ("en-gb", 2))

# (source, medium, campaign, landing) and weights for how new readers arrive.
ACQUISITION = (
    ({"source": "(direct)", "medium": "(none)", "campaign": "(direct)"}, "home", 22),
    ({"source": "google", "medium": "organic", "campaign": "(organic)"}, "article", 34),
    ({"source": "bing", "medium": "organic", "campaign": "(organic)"}, "article", 3),
    ({"source": "facebook", "medium": "social", "campaign": "autumn_share"}, "article", 9),
    ({"source": "threads.net", "medium": "referral", "campaign": "(referral)"}, "article", 6),
    ({"source": "github.com", "medium": "referral", "campaign": "(referral)"}, "article", 8),
    ({"source": "google", "medium": "cpc", "campaign": "data_course_ads"}, "home", 6),
    ({"source": "newsletter", "medium": "email", "campaign": "weekly_digest"}, "article", 4),
    ({"source": "medium.com", "medium": "referral", "campaign": "(referral)"}, "article", 8),
)

# Hour-of-day traffic shape in the property time zone (Asia/Taipei).
HOURLY = (1, 0.6, 0.4, 0.3, 0.3, 0.5, 1, 2, 3.5, 4, 4, 4, 5, 4.5, 4, 4, 4, 4.5, 5, 6, 7, 7.5, 6, 3)

# How deep each persona reads: probability of reaching each read_progress mark.
PERSONAS = {
    "skimmer": {"weight": 45, "read": (0.7, 0.35, 0.15, 0.06), "pages": 0.25, "return": 0.08, "act": 0.3},
    "reader": {"weight": 40, "read": (0.95, 0.8, 0.6, 0.45), "pages": 0.45, "return": 0.18, "act": 1.0},
    "fan": {"weight": 15, "read": (0.98, 0.92, 0.85, 0.75), "pages": 0.6, "return": 0.35, "act": 2.2},
}

# Popularity: a few articles take most of the traffic (Zipf-ish).
ARTICLE_WEIGHTS = {a.id: 1 / (rank + 1) ** 0.8 for rank, a in enumerate(random.Random(7).sample(ARTICLES, len(ARTICLES)))}


def _pick(rng: random.Random, weighted):
    items, weights = zip(*[(x[:-1] if len(x) > 2 else x[0], x[-1]) for x in weighted])
    return rng.choices(items, weights=weights, k=1)[0]


@dataclass
class Reader:
    user_pseudo_id: str
    first_touch: int
    persona: str
    device: dict
    geo: dict
    acquisition: dict
    landing: str
    preferred_topic: str
    session_number: int = 0
    user_id: str | None = None
    subscribed: bool = False
    last_ts: int | None = None
    user_properties: dict = field(default_factory=dict)
    bookmarks: set = field(default_factory=set)


def new_reader(rng: random.Random, first_touch: int) -> Reader:
    ua = _pick(rng, USER_AGENTS)
    device = parse_user_agent(ua)
    device["language"] = _pick(rng, LANGUAGES)
    device["web_info"]["hostname"] = "pixel-notes.local"
    pseudo_id = f"{rng.randrange(10**9, 2**31)}.{first_touch // MICROS}"
    acquisition, landing = _pick(rng, ACQUISITION)
    persona = rng.choices(list(PERSONAS), [p["weight"] for p in PERSONAS.values()])[0]
    return Reader(
        user_pseudo_id=pseudo_id,
        first_touch=first_touch,
        persona=persona,
        device=device,
        geo=geo_for_visitor(pseudo_id),
        acquisition=dict(acquisition),
        landing=landing,
        preferred_topic=rng.choice(list(TOPICS)),
    )


class SessionBuilder:
    """Emits the rows of one visit, advancing a virtual clock as the reader moves."""

    def __init__(self, rng: random.Random, reader: Reader, start: int, traffic: dict | None, landing: str):
        self.rng = rng
        self.reader = reader
        self.clock = start
        self.traffic = traffic
        self.landing = landing
        self.rows: list[dict] = []
        self.page_views = 0
        self.engaged = False
        self.engagement_ms = 0
        self.page = {"page_location": SITE + "/", "page_title": "首頁 · Pixel Notes", "page_referrer": ""}
        self.bundle = 0
        self.bundle_index = 0
        self._page_started = start
        reader.session_number += 1
        self.session_id = start // MICROS
        self.pending_traffic = {"first_visit", "session_start", "page_view"} if traffic else set()

    # ---- primitives -----------------------------------------------------------
    def wait(self, seconds: float) -> None:
        self.clock += int(seconds * MICROS) + self.rng.randrange(1000, 90_000)

    def emit(self, name: str, **params) -> None:
        r = self.reader
        if not self.engaged and (self.engagement_ms >= 10_000 or self.page_views >= 2):
            self.engaged = True
        base = {
            "ga_session_id": self.session_id,
            "ga_session_number": r.session_number,
            "page_location": self.page["page_location"],
            "page_title": self.page["page_title"],
            "engaged_session_event": 1 if self.engaged else 0,
        }
        if self.engaged:
            base["session_engaged"] = "1"
        base.update(params)
        collected = None
        if name in self.pending_traffic:
            collected = self.traffic
            self.pending_traffic.discard(name)
        self.rows.append(
            ga4.build_event_row(
                event_name=name,
                event_timestamp=self.clock,
                user_pseudo_id=r.user_pseudo_id,
                params=base,
                user_id=r.user_id,
                user_properties=r.user_properties,
                user_first_touch_timestamp=r.first_touch,
                device=r.device,
                geo=r.geo,
                traffic_source=r.acquisition,
                collected_traffic_source=collected,
                event_previous_timestamp=r.last_ts,
                event_bundle_sequence_id=self.bundle,
                event_server_timestamp_offset=self.rng.randrange(80_000, 1_500_000),
                batch_event_index=self.bundle_index,
            )
        )
        r.last_ts = self.clock
        self.bundle_index += 1
        self.clock += self.rng.randrange(5_000, 400_000)

    def page_view(self, path: str, title: str, **params) -> None:
        if self.page_views:
            self.engagement()
        self.bundle += 1
        self.bundle_index = 0
        referrer = self.page["page_location"] if self.page_views else _referrer(self.traffic)
        self.page = {"page_location": SITE + path, "page_title": f"{title} · Pixel Notes"}
        self.page_views += 1
        self.emit("page_view", page_referrer=referrer, **params)

    def engagement(self) -> None:
        ms = max(0, (self.clock - self._page_started) // 1000)
        if ms:
            self.engagement_ms += ms
            self.emit("user_engagement", engagement_time_msec=ms)

    # ---- journeys --------------------------------------------------------------
    def run(self) -> list[dict]:
        r, rng = self.reader, self.rng
        persona = PERSONAS[r.persona]
        self.bundle = 1
        if r.session_number == 1:
            self.emit("first_visit")
        self.emit("session_start")

        if r.user_id and r.session_number > 1 and rng.random() < 0.15:
            self.login()
        article = self.pick_article() if self.landing == "article" else None
        if article:
            self.article_page(article)
        else:
            self.home()

        while rng.random() < persona["pages"] and self.page_views < 12:
            roll = rng.random()
            if roll < 0.12:
                self.search()
            elif roll < 0.2:
                self.topic_page()
            elif roll < 0.32 and not r.user_id:
                self.auth()
            elif roll < 0.37 and r.bookmarks:
                self.bookmarks_page()
            else:
                self.select(self.pick_article(), "related_articles" if article else "latest")

        if not r.subscribed and rng.random() < 0.03 * persona["act"] * (2 if self.page_views > 2 else 1):
            self.wait(rng.uniform(2, 10))
            r.subscribed = True
            r.user_properties["newsletter_subscriber"] = "yes"
            self.emit("subscribe_newsletter", newsletter="weekly_digest", already_subscribed=0, form_location="footer")

        self.wait(rng.uniform(1, 20))
        self.engagement()
        return self.rows

    def pick_article(self) -> Article:
        weights = [
            ARTICLE_WEIGHTS[a.id] * (2.5 if a.topic == self.reader.preferred_topic else 1)
            for a in ARTICLES
        ]
        return self.rng.choices(ARTICLES, weights=weights, k=1)[0]

    def mark_page_start(self) -> None:
        self._page_started = self.clock

    def home(self) -> None:
        self.page_view("/", "首頁", content_group="home")
        self.mark_page_start()
        self.wait(self.rng.uniform(3, 25))
        if self.rng.random() < 0.3:
            self.emit("scroll", percent_scrolled=90)
            self.wait(self.rng.uniform(1, 5))
        if self.rng.random() < 0.75:
            self.select(self.pick_article(), "latest")

    def select(self, article: Article, list_name: str) -> None:
        self.emit("select_content", content_type="article", content_id=article.id, item_list_name=list_name, **article_params(article))
        self.article_page(article)

    def topic_page(self) -> None:
        topic = self.reader.preferred_topic if self.rng.random() < 0.7 else self.rng.choice(list(TOPICS))
        self.page_view(f"/topics/{topic}", TOPICS[topic], content_group="topic", topic=topic)
        self.mark_page_start()
        self.wait(self.rng.uniform(3, 15))
        options = [a for a in ARTICLES if a.topic == topic]
        if options and self.rng.random() < 0.7:
            self.select(self.rng.choice(options), f"topic_{topic}")

    def search(self) -> None:
        article = self.pick_article()
        term = self.rng.choice(article.tags + (TOPICS[article.topic],))
        self.wait(self.rng.uniform(2, 8))
        self.emit("search", search_term=term)
        self.page_view(f"/search?q={term}", f"搜尋：{term}", content_group="search")
        self.mark_page_start()
        hits = [a for a in ARTICLES if term.lower() in (a.title + a.summary + " ".join(a.tags) + TOPICS[a.topic]).lower()]
        self.emit("view_search_results", search_term=term, search_results=len(hits))
        self.wait(self.rng.uniform(2, 12))
        if hits and self.rng.random() < 0.65:
            self.select(self.rng.choice(hits), "search_results")

    def bookmarks_page(self) -> None:
        self.page_view("/bookmarks", "我的收藏", content_group="bookmarks")
        self.mark_page_start()
        self.wait(self.rng.uniform(2, 8))
        ids = sorted(self.reader.bookmarks)
        article = next(a for a in ARTICLES if a.id == self.rng.choice(ids))
        self.select(article, "bookmarks")

    def auth(self) -> None:
        r = self.reader
        self.page_view("/login", "登入 / 註冊", content_group="account")
        self.mark_page_start()
        self.wait(self.rng.uniform(8, 40))
        if self.rng.random() < 0.6:
            method = "github" if self.rng.random() < 0.35 else "email"
            r.user_id = f"reader-{self.rng.randrange(36**6):06x}"
            r.user_properties["signed_up"] = "yes"
            self.emit("sign_up", method=method)
            self.home()

    def login(self) -> None:
        self.page_view("/login", "登入 / 註冊", content_group="account")
        self.mark_page_start()
        self.wait(self.rng.uniform(5, 20))
        self.emit("login", method="github" if self.rng.random() < 0.35 else "email")

    def article_page(self, article: Article) -> None:
        rng, persona = self.rng, PERSONAS[self.reader.persona]
        params = article_params(article)
        self.page_view(f"/articles/{article.id}", article.title, **params)
        self.mark_page_start()
        started = self.clock
        seconds_per_quarter = article.reading_time_min * 60 / 4 * rng.uniform(0.5, 1.6)
        reached = 0
        for mark, p in zip((25, 50, 75, 100), persona["read"]):
            if rng.random() > p:
                break
            self.wait(seconds_per_quarter)
            reached = mark
            self.emit("read_progress", percent_read=mark, seconds_on_page=(self.clock - started) // MICROS, **params)
            if mark == 100:
                self.emit("scroll", percent_scrolled=90)
            if mark == 50 and article.code and rng.random() < 0.12 * persona["act"]:
                self.emit("copy_code", code_lines=article.code.count("\n") + 1, **params)
        if reached < 25:
            self.wait(rng.uniform(2, 20))

        act = persona["act"] * (1 + reached / 100)
        if article.links and rng.random() < 0.08 * act:
            label, url = rng.choice(article.links)
            self.emit("click", link_url=url, link_domain=url.split("/")[2], link_text=label + " ↗", outbound=1)
        if article.download and rng.random() < 0.07 * act:
            self.emit("file_download", file_name=f"/files/{article.download}", file_extension=article.download.rsplit(".", 1)[1],
                      link_url=f"{SITE}/files/{article.download}", link_text=f"⬇ 下載 {article.download}")
        if rng.random() < 0.10 * act:
            self.emit("like_article", **params)
        if article.id not in self.reader.bookmarks and rng.random() < 0.05 * act:
            self.reader.bookmarks.add(article.id)
            self.emit("bookmark_article", **params)
        if rng.random() < 0.04 * act:
            method = rng.choices(["copy_link", "x", "facebook"], [5, 2, 3])[0]
            self.emit("share", method=method, content_type="article", item_id=article.id, **params)
        if reached == 100 and rng.random() < 0.05 * act:
            self.wait(rng.uniform(20, 90))
            self.emit("submit_comment", comment_length=rng.randrange(8, 200), logged_in=1 if self.reader.user_id else 0, **params)


def _referrer(traffic: dict | None) -> str:
    if not traffic or traffic.get("medium") in (None, "(none)"):
        return ""
    source = traffic["source"]
    if traffic["medium"] == "organic":
        return f"https://www.{source}.com/"
    if traffic["medium"] == "referral":
        return f"https://{source}/"
    if source == "facebook":
        return "https://l.facebook.com/"
    return ""


def session_traffic(rng: random.Random, reader: Reader) -> tuple[dict | None, str]:
    """Traffic for a visit: first visits use acquisition, returns are mostly direct."""
    if reader.session_number == 0:
        acq = reader.acquisition
        return (None if acq["medium"] == "(none)" else dict(acq)), reader.landing
    if reader.subscribed and rng.random() < 0.35:
        return {"source": "newsletter", "medium": "email", "campaign": "weekly_digest"}, "article"
    if rng.random() < 0.25:
        return {"source": "google", "medium": "organic", "campaign": "(organic)"}, "article"
    return None, "home"


def _random_time_on(rng: random.Random, day: date, tz) -> int:
    hour = rng.choices(range(24), HOURLY)[0]
    dt = datetime.combine(day, dtime(hour, rng.randrange(60), rng.randrange(60)), tzinfo=tz)
    return int(dt.timestamp() * MICROS) + rng.randrange(MICROS)


def generate_history(
    *,
    users: int,
    days: int,
    end_date: date,
    seed: int = 42,
    duplicate_rate: float = 0.0,
) -> Iterator[dict]:
    """Yield GA4 rows for ``users`` new readers over ``days`` days ending at ``end_date``.

    Readers join on a random day (traffic grows over the window) and keep
    returning with a persona-dependent probability, so retention, sessions
    per user and cohort analyses all have something to find.
    """
    rng = random.Random(seed)
    tz = ga4.property_timezone()
    start_date = end_date - timedelta(days=days - 1)
    all_days = [start_date + timedelta(days=i) for i in range(days)]
    join_weights = [1 + i / max(1, days - 1) for i in range(days)]  # mild growth

    visits: list[tuple[int, int, Reader]] = []
    for n in range(users):
        day = rng.choices(all_days, join_weights)[0]
        first = _random_time_on(rng, day, tz)
        reader = new_reader(rng, first)
        visits.append((first, n, reader))
        persona = PERSONAS[reader.persona]
        next_day = day + timedelta(days=1)
        while next_day <= end_date:
            decay = 0.97 ** (next_day - day).days
            if rng.random() < persona["return"] * decay:
                visits.append((_random_time_on(rng, next_day, tz), n, reader))
            next_day += timedelta(days=1)

    visits.sort(key=lambda v: (v[0], v[1]))
    for start, _, reader in visits:
        traffic, landing = session_traffic(rng, reader)
        for row in SessionBuilder(rng, reader, start, traffic, landing).run():
            yield row
            if duplicate_rate and rng.random() < duplicate_rate:
                yield row  # at-least-once delivery: the same hit sent twice


def stream(
    sink,
    *,
    sessions_per_minute: float = 10,
    duration_s: float | None = None,
    seed: int | None = None,
    returning_share: float = 0.35,
    on_row=None,
) -> int:
    """Produce live traffic: new sessions start now and their events are written
    when their (virtual) time arrives, so files grow like a real collector's.
    """
    rng = random.Random(seed)
    readers: list[Reader] = []
    pending: list[tuple[int, int, dict]] = []
    counter = 0
    written = 0
    started = time.time()
    next_session = time.time()
    while duration_s is None or time.time() - started < duration_s:
        now = time.time()
        while next_session <= now:
            start = int(next_session * MICROS)
            if readers and rng.random() < returning_share:
                reader = rng.choice(readers)
            else:
                reader = new_reader(rng, start)
                readers.append(reader)
            traffic, landing = session_traffic(rng, reader)
            for row in SessionBuilder(rng, reader, start, traffic, landing).run():
                counter += 1
                heapq.heappush(pending, (row["event_timestamp"], counter, row))
            next_session += rng.expovariate(sessions_per_minute / 60)
        due = []
        now_micros = int(time.time() * MICROS)
        while pending and pending[0][0] <= now_micros:
            due.append(heapq.heappop(pending)[2])
        if due:
            sink.write_many(due)
            sink.flush()
            written += len(due)
            if on_row:
                for row in due:
                    on_row(row)
        time.sleep(0.2)
    return written
