# 性能测试报告

- 场景：`load`　并发：20　持续：60s　压测器：自研轻量 runner（requests + 线程）
- 被测服务：http://127.0.0.1:65204　环境：Windows-10-10.0.26200-SP0 / Python 3.11.4
- 生成时间：2026-10-26T19:42:52

## 1. 总览

| 指标 | 数值 |
|---|---:|
| 总请求 | 5141 |
| 成功 / 失败 | 5136 / 5 |
| 错误率 | 0.10% |
| 实际 RPS | 85.2 |
| 平均 / P50 | 176.9 / 78.5 ms |
| P90 / P95 / P99 | 319.6 / 649.4 / 2011.6 ms |
| 最大耗时 | 5018.6 ms |

## 2. 门禁判定

| 标准 | 实测 | 结论 |
|---|---|---|
| 错误率 ≤ 1% | 0.10% | ✅ 通过 |
| P95 ≤ 500ms | 649.4ms | ❌ 未通过 |
| 无 5xx | 0.00% | ✅ 通过 |

## 3. 分接口

| 接口 | 请求数 | 失败 | 错误率 | 平均 | P95 | P99 |
|---|---:|---:|---:|---:|---:|---:|
| create_order | 2542 | 3 | 0.12% | 214.9ms | 989.3ms | 2247.2ms |
| get_order | 1039 | 0 | 0.00% | 51.3ms | 149.2ms | 226.1ms |
| list_orders | 780 | 0 | 0.00% | 91.3ms | 219.0ms | 301.0ms |
| pay_order | 511 | 1 | 0.20% | 257.6ms | 874.4ms | 2324.8ms |
| cancel_order | 249 | 1 | 0.40% | 333.4ms | 1599.4ms | 2689.6ms |
| login | 20 | 0 | 0.00% | 9.8ms | 21.3ms | 21.6ms |

## 4. 错误分布

| 次数 | 错误 |
|---:|---|
| 3 | `create_order | ReadTimeout: HTTPConnectionPool(host='127.0.0.1', port=65204): Read timed out. (read timeout=5.0)` |
| 1 | `cancel_order | ReadTimeout: HTTPConnectionPool(host='127.0.0.1', port=65204): Read timed out. (read timeout=5.0)` |
| 1 | `pay_order | ReadTimeout: HTTPConnectionPool(host='127.0.0.1', port=65204): Read timed out. (read timeout=5.0)` |

## 5. 瓶颈线索

- 出现超时：检查线程池/连接池上限，以及同步调用下游（支付网关）是否拖住了请求。
- `pay_order` 的 P95 明显高于查询接口：支付是同步串行调用外部网关，应关注网关超时设置、重试策略，以及是否该改成异步回调。
- P95 远高于平均值：存在长尾请求，通常是锁等待、GC 或慢查询，需要看单请求耗时分布。

## 7. 结论与建议

- 结论：
- 建议：

> 原始数据：`load-20261026-194151/summary.json`、`load-20261026-194151/timeseries.csv`
