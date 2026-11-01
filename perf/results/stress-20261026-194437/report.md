# 性能测试报告

- 场景：`stress`　并发：40　持续：60.0s　压测器：自研轻量 runner（requests + 线程）
- 被测服务：http://127.0.0.1:63137　环境：Windows-10-10.0.26200-SP0 / Python 3.11.4
- 生成时间：2026-10-26T19:45:38

## 1. 总览

| 指标 | 数值 |
|---|---:|
| 总请求 | 5060 |
| 成功 / 失败 | 5056 / 4 |
| 错误率 | 0.08% |
| 实际 RPS | 83.7 |
| 平均 / P50 | 348.3 / 235.6 ms |
| P90 / P95 / P99 | 680.1 / 995.7 / 2437.5 ms |
| 最大耗时 | 5013.6 ms |

## 2. 门禁判定

| 标准 | 实测 | 结论 |
|---|---|---|
| 错误率 ≤ 1% | 0.08% | ✅ 通过 |
| P95 ≤ 500ms | 995.7ms | ❌ 未通过 |
| 无 5xx | 0.00% | ✅ 通过 |

## 3. 分接口

| 接口 | 请求数 | 失败 | 错误率 | 平均 | P95 | P99 |
|---|---:|---:|---:|---:|---:|---:|
| create_order | 2516 | 2 | 0.08% | 395.9ms | 1304.1ms | 2578.6ms |
| get_order | 997 | 0 | 0.00% | 212.2ms | 547.3ms | 831.0ms |
| list_orders | 724 | 0 | 0.00% | 266.3ms | 688.1ms | 900.5ms |
| pay_order | 533 | 1 | 0.19% | 448.4ms | 1284.5ms | 2690.1ms |
| cancel_order | 250 | 1 | 0.40% | 416.0ms | 1110.6ms | 2375.5ms |
| login | 40 | 0 | 0.00% | 10.8ms | 19.1ms | 26.8ms |

## 4. 错误分布

| 次数 | 错误 |
|---:|---|
| 2 | `create_order | ReadTimeout: HTTPConnectionPool(host='127.0.0.1', port=63137): Read timed out. (read timeout=5.0)` |
| 1 | `cancel_order | ReadTimeout: HTTPConnectionPool(host='127.0.0.1', port=63137): Read timed out. (read timeout=5.0)` |
| 1 | `pay_order | ReadTimeout: HTTPConnectionPool(host='127.0.0.1', port=63137): Read timed out. (read timeout=5.0)` |

## 5. 瓶颈线索

- 出现超时：检查线程池/连接池上限，以及同步调用下游（支付网关）是否拖住了请求。
- 写接口 `create_order` 的 P95 超过阈值：本服务底层是 SQLite，**单写锁**会让并发写排队，这是当前部署形态的容量上限。判断方法：看 `timeseries.csv` 里 TPS 是否在某个并发点后不再上升。生产应使用 PostgreSQL/MySQL，或把写操作收敛到单队列。

## 6. 结论与建议

- 结论：未通过：P95 ≤ 500ms。需先定位瓶颈，再用同一场景复测定论。
- 建议：
  - 先看「瓶颈线索」和 `timeseries.csv` 的 TPS 曲线，确认是锁等待、下游阻塞还是线程池打满；
  - 修复后**用同一 profile 重跑**，报告会自动和上一次对比，形成性能基线；
  - 结论只写在报告里不算完，要能落到一个具体的优化项和负责人。

> 原始数据：`stress-20261026-194437/summary.json`、`stress-20261026-194437/timeseries.csv`
