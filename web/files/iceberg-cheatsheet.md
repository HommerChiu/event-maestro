# Iceberg Cheatsheet

| 操作 | Spark SQL |
| --- | --- |
| 時間旅行 | `SELECT * FROM t VERSION AS OF 123` |
| 看 snapshot | `SELECT * FROM t.snapshots` |
| 合併小檔 | `CALL system.rewrite_data_files('db.t')` |
| 清舊 snapshot | `CALL system.expire_snapshots('db.t', TIMESTAMP '2026-01-01')` |
| 改分區 | `ALTER TABLE t ADD PARTITION FIELD days(event_ts)` |
