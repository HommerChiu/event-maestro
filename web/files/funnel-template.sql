-- 閱讀漏斗：進站 → 看文章 → 讀一半 → 讀完 → 訂閱
with ev as (
  select user_pseudo_id, event_name,
    (select value.int_value from unnest(event_params) where key = 'percent_read') as percent_read
  from ga4_events
)
select
  count(distinct user_pseudo_id) as visitors,
  count(distinct if(event_name = 'select_content', user_pseudo_id, null)) as opened_article,
  count(distinct if(percent_read >= 50, user_pseudo_id, null)) as read_half,
  count(distinct if(percent_read = 100, user_pseudo_id, null)) as finished,
  count(distinct if(event_name = 'subscribe_newsletter', user_pseudo_id, null)) as subscribed
from ev;
