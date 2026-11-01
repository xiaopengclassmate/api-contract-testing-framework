# 性能测试（场景脚本 + 轻量 runner + 实测报告）

接口测完之后，下一个问题一定是：**这套服务能扛多少并发？拐点在哪？**

这个目录回答它。目标不是把 QPS 刷得多高，而是建立一套**可重复、能对比、能找到瓶颈**的性能测试方式：

- 业务场景按真实流量比例建模，而不是单接口狂刷；
- 每次跑完自动出 Markdown 报告、JSON 原始数据、逐秒时间线；
- 同一场景重复跑会自动和上一次对比，形成**性能基线**；
- 报告里给出可解释的瓶颈线索，而不是只丢一张 P95 表。

> 本机环境装不了 Locust（无外网），所以 runner 用 `requests + 线程` 手写，逻辑透明；
> `perf/locustfile.py` 提供了同场景、同权重的 Locust 版本，环境允许时可直接切换。

---

## 1. 目录结构

```text
perf/
├── run_perf.py       # 编排：起支付网关替身 → 起被测服务 → 跑场景 → 出报告
├── loadgen.py        # 压测器：虚拟用户、业务权重、百分位统计、报告生成
├── fake_gateway.py   # 支付网关替身（可控返回、可注入延迟）
├── locustfile.py     # 等价 Locust 脚本（有依赖时使用）
├── results/          # 每次运行的 report.md / summary.json / timeseries.csv
└── .data/            # 压测用临时 SQLite（不入库）
```

---

## 2. 快速开始

在项目根目录：

```bash
# 基准场景：5 并发、30 秒
python -m perf.run_perf --profile baseline

# 负载场景：20 并发、60 秒
python -m perf.run_perf --profile load

# 压力场景：40 并发
python -m perf.run_perf --profile stress

# 自定义
python -m perf.run_perf --users 30 --duration 120 --spawn-rate 5 --think-time 0.2

# 模拟下游支付网关变慢（验证超时/降级）
python -m perf.run_perf --profile load --gateway-delay-ms 1500
```

一条命令会自动完成：建独立数据库 → 起网关替身 → 起 uvicorn → 等 `/health` → 压测 → 出报告 → 清理。

参数：

| 参数 | 说明 | 默认 |
|---|---|---|
| `--profile` | `smoke/baseline/load/stress/spike/soak` | `baseline` |
| `--users` | 并发虚拟用户数 | 按 profile |
| `--duration` | 持续秒数 | 按 profile |
| `--spawn-rate` | 每秒拉起用户数（模拟爬坡） | 按 profile |
| `--think-time` | 每个请求后的随机等待上限（秒） | 按 profile |
| `--gateway-delay-ms` | 支付网关替身延迟，用于故障注入 | 0 |
| `--keep-db` | 保留压测数据库，便于事后查数据 | 关 |

---

## 3. 场景定义

| 场景 | 并发 | 时长 | 爬坡 | 目的 |
|---|---:|---:|---:|---|
| `smoke` | 1 | 10s | 1/s | 脚本自检，确认链路通 |
| `baseline` | 5 | 30s | 5/s | 建立基线，后续都跟它比 |
| `load` | 20 | 60s | 5/s | 预期业务峰值，看是否满足 SLO |
| `stress` | 40 | 90s | 2/s | 持续加压，找容量拐点 |
| `spike` | 40 | 30s | 40/s | 瞬间打入，看恢复能力（大促/直播场景） |
| `soak` | 10 | 300s | 2/s | 长稳，发现内存泄漏与连接泄漏 |

业务权重按订单服务真实特征建模（写多读少）：

| 动作 | 权重 | 说明 |
|---|---:|---|
| 创建订单 | 50% | 主写路径，SQLite 锁竞争主要来源 |
| 查询订单详情 | 20% | 读路径 |
| 查询订单列表 | 15% | 带分页与过滤，含 `count(*)` |
| 支付订单 | 10% | 同步调用下游网关 |
| 取消订单 | 5% | 状态流转 |

每个虚拟用户使用独立 `customer_id`，登录一次后复用 Token，订单数据互不干扰——和真实用户行为一致。

---

## 4. 指标口径

| 指标 | 定义 | 为什么看它 |
|---|---|---|
| RPS/TPS | 总请求数 ÷ 实际运行时长 | 吞吐能力，注意不是"配置的并发数" |
| RT 平均 | 所有请求耗时均值 | 只作参考，会被长尾拉偏 |
| P90/P95/P99 | 分位耗时 | **SLO 看 P95/P99**，用户体验由长尾决定 |
| 错误率 | 失败请求 ÷ 总请求 | 含 HTTP 非预期码、超时、连接异常 |
| 5xx 率 | 服务端错误占比 | 单独拎出来，前端 4xx 通常是用例问题 |
| 拐点 | RPS 不再上升、RT 开始飙升的并发点 | 容量规划的依据 |

---

## 5. 实测结果（2026-10-26，Windows 11 / Python 3.11.4 / SQLite）

| 场景 | 并发 | 总请求 | RPS | 平均 | P95 | P99 | 错误率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 5 | 1,254 | 41.6 | 19.4ms | 42.5ms | 60.1ms | 0.00% |
| load | 20 | 5,082 | 84.2 | 178.2ms | 637.0ms | 2,148.0ms | 0.04% |
| stress | 40 | 5,060 | 83.7 | 348.3ms | 995.7ms | 2,437.5ms | 0.08% |

**拐点结论**：并发从 20 加到 40，RPS 几乎不变（84.2 → 83.7），P95 翻倍（637ms → 996ms）。

这说明系统在 **~85 RPS** 附近已经饱和，继续加并发只会让请求排队。定位到三层原因：

1. **数据库**：SQLite 是单写锁，写并发上来后在数据库层串行化——压测日志里能看到 `database is locked`，日志中 `create_order` 的 P95（1,039ms）远高于 `get_order`（143ms）；
2. **应用**：同步 `def` 接口跑在 FastAPI 线程池里，线程被写等待占满后，读请求也被拖慢；
3. **下游**：`pay_order` 同步调用网关，P95 1,124ms，属于外部依赖放大。

这份结论的价值不在于"服务很慢"，而在于：**知道慢在哪一层、怎么验证、换成生产形态（PostgreSQL + 连接池 + 异步回调）后该复测什么**。

> 详细报告见 `results/<场景>-<时间戳>/report.md`，逐秒 TPS 见同目录 `timeseries.csv`。

---

## 6. 报告里有什么

每次运行生成一个目录：

```text
results/load-20261026-194327/
├── report.md        # 人看的：总览、门禁、分接口、错误分布、瓶颈线索、与上次对比、结论
├── summary.json     # 机器看的：可入监控、可做 CI 阈值判断
└── timeseries.csv   # 逐秒 requests/errors/TPS/avg/P95，可直接画图
```

门禁（`loadgen.THRESHOLDS`，可改）：

- 错误率 ≤ 1%
- 全局 P95 ≤ 500ms
- 无 5xx

任一不通过，`run_perf.py` 以退出码 1 结束——可以直接挂到 CI 上当性能门禁。

同 profile 重跑会自动读取上一次的 `summary.json`，在报告里给出 RPS / P95 变化百分比。

---

## 7. 换 Locust 跑

```bash
pip install locust

python -m perf.run_perf --profile baseline   # 只是先起服务；也可以自己 uvicorn app.main:app
locust -f perf/locustfile.py --host http://127.0.0.1:18000

# 无头模式，适合 CI
locust -f perf/locustfile.py --host http://127.0.0.1:18000 \
    --headless -u 20 -r 5 -t 60s --only-summary
```

Locust 版本与自研 runner 的权重、数据隔离方式一致，两者结果可以互相印证。

---

## 8. 已知局限（面试被问要主动说）

1. **压测器与被测服务同机**：CPU 互相抢，绝对 RPS 偏低；企业里压测机与被测环境必须隔离。
2. **未采集服务端指标**：本机没有 `psutil`/Prometheus，报告里没有 CPU、内存、GC、连接池、慢查询。生产压测必须补这一层，否则只能看到"慢了"，看不到"为什么慢"。
3. **SQLite 不是生产形态**：锁行为与 PostgreSQL/MySQL 完全不同，结论只适用于当前部署。生产压测应在同构环境做。
4. **单机单进程**：没有多实例、负载均衡、网络延迟因素。
5. **支付网关为本地替身**：能验证编排与超时，但不能代表真实网关的抖动与限流。

---

## 9. 接 CI 的建议

```yaml
- name: Performance baseline
  run: python -m perf.run_perf --profile baseline
- uses: actions/upload-artifact@v4
  with:
    name: perf-report
    path: perf/results/
```

- 每次 PR 只跑 `baseline`（30 秒），守住"没有明显退化"；
- 每晚跑 `load` + `soak`，把结果写入趋势库；
- 性能门禁要和功能门禁分开：性能失败不一定要阻断合并，但必须有人看。

---

## 10. 面试/入职怎么讲（三句话版本）

1. 我按真实流量比例建模，不是单接口压；写多读少，所以写路径的锁竞争是主要矛盾。
2. 我找到了拐点：20 并发 84 RPS，40 并发还是 84 RPS、P95 翻倍，瓶颈在 SQLite 单写锁，日志里有 `database is locked` 佐证。
3. 我的报告能自动和上一次对比，所以它不是一次性截图，而是一条可回归的性能基线。
