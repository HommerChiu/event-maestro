# 閱讀網站的星狀模型

```
            dim_reader
                |
dim_date -- fct_article_reads -- dim_article -- dim_author
                |
           dim_traffic_source
```

- fct_article_reads grain：一位讀者在一個 session 內對一篇文章的閱讀
- measures：max_percent_read、engagement_time_msec、liked、bookmarked、shared
