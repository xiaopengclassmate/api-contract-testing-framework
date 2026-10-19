# 简历项目条目：接口自动化 + 契约测试

> 已写入你的简历文件：
>
> - `C:\Users\15830\Desktop\测试简历\彭文涛-测试开发-简历-接口契约方向.pdf`（两页版）
> - `C:\Users\15830\Desktop\测试简历\彭文涛-测试开发-简历-接口契约方向-一页版.pdf`（一页版）
> - `C:\Users\15830\Desktop\测试简历\彭文涛-测试开发-简历-接口契约方向.json`
>
> 原始 `新建简历 731b91.json` 未被修改。生成版只保留本项目，未使用
> `bishe` / 农产品项目的任何内容。重新生成可运行
> `C:\Users\15830\Desktop\测试简历\build_resume_pdf.py`。
>
> 面试现场怎么演示：见 [`interview-demo.md`](interview-demo.md)。
>
> 项目仓库：<https://github.com/xiaopengclassmate/api-contract-testing-framework>
> GitHub Actions：<https://github.com/xiaopengclassmate/api-contract-testing-framework/actions/workflows/api-tests.yml>
> 在线 Allure：<https://xiaopengclassmate.github.io/api-contract-testing-framework/>（启用 Pages 后生效）

## 完整版（推荐，5 条）

### 订单服务接口自动化与契约测试框架 | 测试开发（个人项目） | 2026.10 - 至今

- 独立设计并实现 FastAPI 订单服务作为被测系统，基于 Pytest + Requests 搭建 HTTP E2E、JSON Schema 契约、SQLAlchemy 数据库断言、responses 外部依赖 Mock、Hypothesis 属性测试与接口安全基线六层测试体系，设计 87 条高价值用例（41 接口 / 16 契约 / 4 数据库 / 9 Mock / 13 安全 / 4 属性），服务端语句覆盖率 100%（247 statements）。
- 基于 JSON Schema Draft 2020-12 与 OpenAPI 3.1 实现契约校验，支持跨文件 `$ref` 解析、Provider/Consumer 字段一致性比对和额外字段拦截，可在 CI 阶段拦截字段缺失、类型变更等破坏性变更。
- 使用 responses 对支付网关做故障注入，9 条支付用例覆盖 500、超时、非 JSON、缺失流水号等异常场景，验证 502/504 降级及订单 FAILED 状态落库；通过临时 SQLite、动态测试数据和用例级清理实现用例隔离。
- 基于 Hypothesis 构建 4 条属性测试，每条运行 25 组随机数据，自动验证金额汇总、商品顺序无关、取消终态和软删除不变量；补充 13 条安全用例覆盖批量赋值、SQL 注入、畸形 JWT、错误信息泄露与安全响应头。
- 搭建 GitHub Actions + Allure + pytest-html + coverage 流水线，配置 95% 覆盖率门禁、Allure Pages 发布与 Docker 镜像构建，支持一条命令完成回归并输出可追溯报告。

## 一页精简版（空间不足时用 3 条）

### 订单服务接口自动化与契约测试框架 | 测试开发（个人项目） | 2026.10 - 至今

- 基于 Pytest + Requests 搭建 HTTP E2E、JSON Schema 契约、数据库断言、支付网关 Mock、Hypothesis 属性测试与安全基线六层测试体系，设计 87 条用例，服务端语句覆盖率 100%（247 statements）。
- 基于 JSON Schema Draft 2020-12 与 OpenAPI 3.1 实现契约校验和字段一致性比对，支持跨文件 `$ref`，可在 CI 阶段拦截破坏性变更；使用 responses 注入 500、超时、非 JSON 等支付异常，验证 502/504 降级与 FAILED 落库。
- 使用 Hypothesis 自动生成 100 组订单验证金额与状态不变量，补充批量赋值、SQL 注入、畸形 JWT、错误泄露等安全用例；接入 GitHub Actions、Allure 与覆盖率门禁。

## 英文版（投外企时可选）

### API Automation & Contract Testing Framework | Test Developer (Personal Project) | Oct 2026 - Present

- Built a self-contained FastAPI order service and a six-layer test framework (HTTP E2E, JSON Schema contracts, SQLAlchemy DB assertions, payment-gateway mocking, Hypothesis property-based tests, and API security baseline) with 87 high-value tests and 100% statement coverage (247 statements).
- Implemented consumer-driven schema validation with JSON Schema Draft 2020-12 and provider validation against OpenAPI 3.1, including cross-file `$ref` resolution, field-parity checks, and unexpected-field rejection to catch breaking changes in CI.
- Injected payment failures (HTTP 500, timeout, non-JSON, missing reference) with `responses`; verified 502/504 degradation and persisted `FAILED` order states.
- Added four Hypothesis properties (25 generated cases each) for amount invariants, item-order independence, cancellation terminal state, and soft-delete visibility, plus 13 security tests for mass assignment, SQL injection, malformed JWTs, error leakage, and security headers.
- Integrated GitHub Actions, Allure, pytest-html, coverage gates, GitHub Pages and Docker image builds for one-command regression with traceable reports.

## 技能关键词

`Python` `Pytest` `Requests` `FastAPI` `SQLAlchemy` `JSON Schema` `Draft 2020-12` `OpenAPI 3.1` `responses` `Hypothesis` `属性测试` `Property-based Testing` `接口安全` `SQL 注入` `批量赋值` `安全响应头` `Allure` `GitHub Actions` `Docker` `SQLite` `pytest-html` `coverage` `契约测试` `故障注入`

## 面试口径

### 30 秒自述

> 这个项目是我独立做的接口自动化与契约测试专项。被测服务是我用 FastAPI 写的订单服务，测试分成六层：HTTP 端到端、JSON Schema 契约、数据库断言、支付网关 Mock、Hypothesis 属性测试和接口安全基线。项目有 87 条主用例，服务端语句覆盖率 100%，CI 里配置了覆盖率门禁、Allure 报告和 Docker 构建。最有价值的部分是契约测试、支付异常降级和属性测试：字段被破坏性修改会在 CI 直接失败；支付超时/5xx 会验证 502/504 和订单 FAILED 状态是否真正落库；属性测试会自动生成订单组合，比手写用例更容易发现金额和状态流转的隐藏问题。

### 常见追问

| 问题 | 回答要点 |
|---|---|
| 项目代码在哪？ | GitHub 公开仓库 `xiaopengclassmate/api-contract-testing-framework`；`main` 推送后 Actions 中测试 Job 与 Docker Job 均通过，Allure 报告发布到 `gh-pages`。 |
| 为什么是 87 条？ | 自包含 SUT 的高价值用例，按 41 接口 / 16 契约 / 4 数据库 / 9 Mock / 13 安全 / 4 属性分层；另有 2 条第三方契约用例。重点在覆盖质量和分层，不是堆数量。 |
| 100% 覆盖率怎么算的？ | 被测服务 247 条语句、0 miss，统计的是 `app/` 而不是测试代码；覆盖率不等于质量，另有契约负例、故障注入、属性测试和安全基线。 |
| 契约测试和接口测试区别？ | 接口测试验证行为和业务规则；契约测试验证提供方/消费方的字段、类型、必填、枚举约定。当前是 Schema-based，后续可升级 Pact。 |
| `$ref` 怎么处理？ | 用 `referencing.Registry` 把 `schemas/` 下所有文件注册为资源，JSON Schema Draft 2020-12 解析跨文件引用。 |
| 支付网关怎么 Mock？ | `responses` 在进程内拦截 `requests`，用 `add_passthru` 放行本地被测服务；断言发给网关的请求体和返回后的数据库状态。 |
| 为什么返回 504 不是 500？ | 网关超时属于上游超时，语义上用 504 Gateway Timeout；订单标记 FAILED，避免继续支付或取消。 |
| 属性测试和参数化测试区别？ | 参数化是“我给样例”，属性测试是“我给不变量，Hypothesis 生成样例”；失败时自动收缩到最小反例。金额按“分”生成，避免随机浮点误报。 |
| 安全测试做到什么程度？ | 是接口安全基线，不是完整渗透：批量赋值、SQL 注入、畸形 JWT、错误信息泄露、安全响应头、OpenAPI 配置泄露；没有做 RBAC/IDOR、速率限制和完整 OWASP API Top 10。 |
| 批量赋值怎么防？ | 请求模型只接收 `customer_id/currency/items`，`status/total_amount/payment_reference/is_deleted` 由服务端生成；测试额外传这些字段并断言响应和数据库都没有被篡改。 |
| SQL 注入怎么验证？ | 把 `customer' OR '1'='1` 作为客户 ID 创建并查询，断言只返回该订单、数据库保存原字符串，证明使用的是参数化查询而不是字符串拼接。 |
| 用例怎么保证稳定？ | 临时 SQLite、动态 UUID 数据、用例级清库、真实 uvicorn + `/health` 就绪等待、GET 才重试、所有请求带超时；属性测试按“分”生成两位小数金额，并用 Hypothesis 示例数据库复现失败样例。 |
| Docker 跑过吗？ | 已提供 Dockerfile/docker-compose，CI 有独立 `docker-build` Job；本机未装 Docker，如实说明即可。 |

### 不要写/不要吹

- 不要写“精通接口自动化/契约测试”，用“能独立搭建/实现”更稳。
- 不要声称对接过真实支付网关；项目里是 `responses` 故障注入，真实联调是下一步。
- 对本项目，不要把安全基线说成“完整安全测试/渗透测试”，也不要说项目里做过 RBAC、IDOR、速率限制；工作经历中的越权测试按实际经历表述。
- 不要声称做过性能压测（那是另一个项目的内容），避免被追问时答不上来。
- 不要把“覆盖率 100%”说成“没有缺陷”；它只代表语句被执行到。

## 数据口径

| 指标 | 数值 | 来源 |
|---|---:|---|
| 主测试集 | 87 passed | `pytest -q` |
| 接口 E2E | 41 | `tests/api/` |
| 契约 | 16 | `tests/contract/` |
| 数据库 | 4 | `tests/db/` |
| 支付 Mock | 9 | `tests/mock/` |
| 接口安全基线 | 13 | `tests/security/` |
| 属性测试 | 4 条 × 25 组 = 100 组随机订单 | `tests/property/` |
| 服务端覆盖率 | 100%（247 statements） | `pytest --cov=app` |
| 本地耗时 | 约 13 秒 | Windows / Python 3.11.4 |
| 可选第三方契约 | 2 passed | `pytest external_tests` |
| GitHub Actions | success | `api-contract-tests` + `docker-build` |
| 远程仓库 | public | <https://github.com/xiaopengclassmate/api-contract-testing-framework> |
