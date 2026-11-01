# 5 分钟面试演示脚本

> 目标：不只说“我写了 87 条用例”，而是让面试官在 5 分钟内看到
> **测试分层、契约拦截、故障注入、属性测试、安全基线、工程化** 六件事。

## 0. 开场（30 秒）

> 这个项目是我独立做的接口自动化与契约测试专项。被测服务是我用 FastAPI
> 写的订单服务，测试分为六层：HTTP E2E、JSON Schema 契约、数据库断言、
> 支付网关 Mock、Hypothesis 属性测试和接口安全基线。当前 87 条用例全部
> 通过，服务端语句覆盖率 100%，CI 里有覆盖率门禁和 Allure 报告。

## 1. 先看结果（40 秒）

```bash
pytest -q
```

预期：

```text
87 passed in ~13s
TOTAL 247 0 100%
```

讲解点：

- 87 条不是堆数量：41 接口 / 16 契约 / 4 数据库 / 9 Mock / 13 安全 / 4 属性；
- 覆盖率统计的是 `app/` 被测服务，不是测试代码；
- 一次回归十几秒，适合放进每次 push 的 CI。

## 2. 契约测试（60 秒）

```bash
pytest tests/contract -q
```

重点讲：

- `schemas/order.json` 是消费方契约，`schemas/` 下多个文件通过
  `referencing.Registry` 解析跨文件 `$ref`；
- 服务端 `/openapi.json` 用 `openapi-spec-validator` 校验 OpenAPI 3.1；
- `OrderOut` 的必填字段和属性集合与消费者契约逐项比对；
- 负例：缺字段、额外字段都会让契约校验失败。

如果面试官想看“真的会失败”，运行：

```bash
pytest tests/contract/test_contracts.py::TestContracts::test_contract_detects_breaking_change -q
pytest tests/contract/test_contracts.py::TestContracts::test_contract_rejects_unexpected_field -q
```

## 3. 支付故障注入（60 秒）

```bash
pytest tests/mock -q
```

讲解点：

- `responses` 在进程内拦截 `requests`，`add_passthru` 放行本地被测服务；
- 9 条用例覆盖：成功、500、超时、非 JSON、缺 `reference`、重复支付、
  已支付不可取消/删除、已取消不可支付；
- 超时返回 504、网关错误返回 502，订单落库为 `FAILED`；
- 断言不仅看响应，还看发给网关的请求体和数据库状态。

## 4. 属性测试（60 秒）

```bash
pytest tests/property -q
```

讲解点：

- 不是“再写几个样例”，而是验证不变量：
  总价 = 明细小计之和、商品顺序不影响总价、取消是终态、软删除后不可见；
- Hypothesis 每条运行 25 组随机数据，失败会自动收缩到最小反例；
- 金额按“分”生成，避免随机浮点导致误报；
- 适合补人工边界用例没想到的组合。

## 5. 接口安全基线（45 秒）

```bash
pytest tests/security -q
```

讲解点：

- 批量赋值：客户端传 `status=PAID/total_amount=0.01`，服务端必须忽略；
- SQL 注入：`customer' OR '1'='1` 被当作普通字符串，参数化查询不泄露数据；
- 畸形 JWT：Basic、空 Bearer、错误 Scheme、非法 JWT 统一 401；
- 错误响应不泄露堆栈/SQL/路径/口令；
- 安全响应头由中间件统一添加，测试直接回归。

主动说明边界：这是**接口安全基线**，不是完整渗透测试；没有做
RBAC/IDOR、速率限制和完整 OWASP API Top 10。

## 6. 看报告（45 秒）

```bash
run-tests.bat
open-report.bat
```

Allure 中重点展示：

- 87 条用例、100% 通过率；
- Suites 分层：api / contract / security / mock / db / property；
- 每个 HTTP 请求/响应附件，失败时可以直接定位；
- GitHub Actions 中会生成 pytest-html、覆盖率、Allure，并发布 Pages。

## 7. 收尾（30 秒）

> 如果继续演进，我会做三件事：一是把 Schema 契约升级到 Pact + Broker，
> 二是补并发/幂等和 PostgreSQL/Testcontainers，三是把安全基线扩展到
> RBAC/IDOR。当前项目刻意没有做这些，是为了把已做的部分讲清楚、跑稳定。

## 高频追问速查

| 追问 | 一句话回答 |
|---|---|
| 为什么自己写 SUT？ | 企业接口测试常被环境和数据卡住；自带 SUT 让 CI 稳定，也能真实断言数据库和外部依赖。 |
| 为什么不用 TestClient？ | 真实 uvicorn 覆盖 HTTP 序列化、状态码、异常处理和网络栈，更接近线上。 |
| 100% 覆盖率代表质量高吗？ | 不代表；它只说明语句被执行。质量还靠契约负例、故障注入、属性测试和安全基线。 |
| 为什么支付超时返回 504？ | 上游超时语义是 Gateway Timeout；订单标记 FAILED，避免继续支付/取消。 |
| 契约和接口测试区别？ | 接口测试验证行为；契约验证提供方/消费方的字段、类型、必填、枚举约定。 |
| 属性测试和参数化区别？ | 参数化是我给样例；属性测试是我给不变量，Hypothesis 生成样例并收缩反例。 |
| 安全测试做到什么程度？ | 只做可回归的接口基线，不冒充渗透测试；RBAC/IDOR/限流是后续演进。 |

更完整的简历表述与数据口径见 [`resume-entry.md`](resume-entry.md)。
