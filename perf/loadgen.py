"""轻量压测器（只依赖 requests + 标准库）。

为什么不用 Locust/JMeter：
- 这台机器装不了包，压测器必须能直接跑；
- 逻辑透明，面试时能一行行讲清楚 TPS/P95 是怎么算出来的；
- `perf/locustfile.py` 提供了等价的 Locust 版本，环境允许时可以直接切过去。

产出：`perf/results/<profile>-<时间戳>/` 下的 report.md / summary.json / timeseries.csv。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import requests

# 场景参数：users=并发虚拟用户, duration=持续秒数, spawn_rate=每秒拉起用户数
PROFILES: dict[str, dict] = {
    "smoke": {"users": 1, "duration": 10, "spawn_rate": 1, "think_time": 0.5},
    "baseline": {"users": 5, "duration": 30, "spawn_rate": 5, "think_time": 0.2},
    "load": {"users": 20, "duration": 60, "spawn_rate": 5, "think_time": 0.1},
    "stress": {"users": 40, "duration": 90, "spawn_rate": 2, "think_time": 0.1},
    "spike": {"users": 40, "duration": 30, "spawn_rate": 40, "think_time": 0.1},
    "soak": {"users": 10, "duration": 300, "spawn_rate": 2, "think_time": 0.5},
}

# 业务权重：模拟真实流量里“写多读少”的订单服务
ACTION_WEIGHTS: list[tuple[str, int]] = [
    ("create_order", 50),
    ("get_order", 20),
    ("list_orders", 15),
    ("pay_order", 10),
    ("cancel_order", 5),
]

THRESHOLDS = {
    "error_rate": 0.01,      # 错误率 ≤ 1%
    "p95_ms": 500,           # 全局 P95 ≤ 500ms
    "server_error_rate": 0.0,  # 不允许 5xx
}

EXPECTED = {
    "login": 200,
    "create_order": 201,
    "get_order": 200,
    "list_orders": 200,
    "pay_order": 200,
    "cancel_order": 200,
}


@dataclass
class Config:
    base_url: str = "http://127.0.0.1:18000"
    profile: str = "smoke"
    users: int = 1
    duration: float = 10
    spawn_rate: float = 1
    think_time: float = 0.5
    timeout: float = 5.0
    username: str = "admin"
    password: str = "admin123"


@dataclass
class Record:
    ts: float
    action: str
    latency_ms: float
    status: int | None
    ok: bool
    error: str | None = None


@dataclass
class RunResult:
    records: list[Record] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0


class VirtualUser(threading.Thread):
    """一个虚拟用户：登录一次，然后按权重循环发请求。"""

    def __init__(
        self,
        index: int,
        cfg: Config,
        result: RunResult,
        stop_at: float,
    ) -> None:
        super().__init__(daemon=True)
        self.index = index
        self.cfg = cfg
        self.result = result
        self.stop_at = stop_at
        self.session = requests.Session()
        self.customer_id = f"perf-{index}-{uuid.uuid4().hex[:8]}"
        self.order_ids: list[str] = []
        self.pending_ids: list[str] = []
        self.actions, self.weights = zip(*ACTION_WEIGHTS)

    # ---------- 基础设施 ----------

    def _url(self, path: str) -> str:
        return f"{self.cfg.base_url}{path}"

    def _record(
        self,
        action: str,
        started: float,
        status: int | None,
        error: str | None = None,
    ) -> None:
        latency = (time.perf_counter() - started) * 1000
        ok = status == EXPECTED.get(action, 200)
        self.result.records.append(
            Record(
                ts=time.time(),
                action=action,
                latency_ms=round(latency, 2),
                status=status,
                ok=ok,
                error=error if not ok else None,
            )
        )

    def _call(self, action: str, method: str, path: str, **kwargs):
        started = time.perf_counter()
        try:
            resp = self.session.request(
                method, self._url(path), timeout=self.cfg.timeout, **kwargs
            )
        except requests.RequestException as exc:
            self._record(action, started, None, f"{type(exc).__name__}: {exc}")
            return None

        error = None if resp.status_code == EXPECTED.get(action) else (
            f"HTTP {resp.status_code}: {resp.text[:80]}"
        )
        self._record(action, started, resp.status_code, error)
        return resp

    # ---------- 业务动作 ----------

    def login(self) -> bool:
        started = time.perf_counter()
        try:
            resp = self.session.post(
                self._url("/api/v1/auth/token"),
                json={"username": self.cfg.username, "password": self.cfg.password},
                timeout=self.cfg.timeout,
            )
        except requests.RequestException as exc:
            self._record("login", started, None, f"{type(exc).__name__}: {exc}")
            return False

        self._record(
            "login",
            started,
            resp.status_code,
            None if resp.status_code == 200 else f"HTTP {resp.status_code}",
        )
        if resp.status_code != 200:
            return False

        self.session.headers["Authorization"] = (
            f"Bearer {resp.json()['access_token']}"
        )
        return True

    def create_order(self) -> None:
        items = [
            {
                "sku": f"SKU-{random.randint(1000, 9999)}",
                "quantity": random.randint(1, 3),
                "unit_price": round(random.uniform(9.9, 999.0), 2),
            }
            for _ in range(random.randint(1, 3))
        ]
        resp = self._call(
            "create_order",
            "POST",
            "/api/v1/orders",
            json={"customer_id": self.customer_id, "items": items},
        )
        if resp is not None and resp.status_code == 201:
            order_id = resp.json()["id"]
            self.order_ids.append(order_id)
            self.pending_ids.append(order_id)

    def get_order(self) -> None:
        order_id = self._pick_order()
        if order_id:
            self._call("get_order", "GET", f"/api/v1/orders/{order_id}")

    def list_orders(self) -> None:
        self._call(
            "list_orders",
            "GET",
            "/api/v1/orders",
            params={"customer_id": self.customer_id, "limit": 20},
        )

    def cancel_order(self) -> None:
        order_id = self._pick_pending()
        if order_id is None:
            return
        resp = self._call("cancel_order", "POST", f"/api/v1/orders/{order_id}/cancel")
        if resp is not None and resp.status_code == 200:
            self.pending_ids.remove(order_id)

    def pay_order(self) -> None:
        order_id = self._pick_pending()
        if order_id is None:
            return
        resp = self._call("pay_order", "POST", f"/api/v1/orders/{order_id}/pay")
        if resp is not None and resp.status_code == 200:
            self.pending_ids.remove(order_id)

    def _pick_order(self) -> str | None:
        return random.choice(self.order_ids) if self.order_ids else self._create_first()

    def _pick_pending(self) -> str | None:
        if self.pending_ids:
            return random.choice(self.pending_ids)
        return self._create_first()

    def _create_first(self) -> str | None:
        """读/取消/支付需要订单时，先创建一单，保证场景不空转。"""
        self.create_order()
        return self.order_ids[-1] if self.order_ids else None

    # ---------- 主循环 ----------

    def run(self) -> None:
        if not self.login():
            return
        action_map = {
            "create_order": self.create_order,
            "get_order": self.get_order,
            "list_orders": self.list_orders,
            "pay_order": self.pay_order,
            "cancel_order": self.cancel_order,
        }
        while time.time() < self.stop_at:
            action = random.choices(self.actions, weights=self.weights, k=1)[0]
            action_map[action]()
            if self.cfg.think_time:
                time.sleep(random.uniform(0, self.cfg.think_time))
        self.session.close()


# ---------- 统计 ----------

def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    index = max(0, math.ceil(pct / 100 * len(sorted_values)) - 1)
    return sorted_values[index]


def _latency_stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "avg": 0, "p50": 0, "p90": 0, "p95": 0, "p99": 0, "max": 0}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "avg": round(sum(ordered) / len(ordered), 1),
        "p50": round(_percentile(ordered, 50), 1),
        "p90": round(_percentile(ordered, 90), 1),
        "p95": round(_percentile(ordered, 95), 1),
        "p99": round(_percentile(ordered, 99), 1),
        "max": round(ordered[-1], 1),
    }


def _summarize(result: RunResult, cfg: Config) -> dict:
    elapsed = max(result.finished_at - result.started_at, 0.001)
    records = result.records
    errors = [r for r in records if not r.ok]
    server_errors = [r for r in records if r.status and r.status >= 500]

    by_action: dict[str, list[Record]] = {}
    for record in records:
        by_action.setdefault(record.action, []).append(record)

    actions = {}
    for name, items in by_action.items():
        ok_items = [r for r in items if r.ok]
        actions[name] = {
            "requests": len(items),
            "failure": len(items) - len(ok_items),
            "error_rate": round((len(items) - len(ok_items)) / len(items), 4),
            **_latency_stats([r.latency_ms for r in ok_items]),
        }

    error_buckets: dict[str, dict] = {}
    for item in errors:
        key = f"{item.action} | {item.error or 'unknown'}"
        bucket = error_buckets.setdefault(key, {"count": 0, "sample": item.error})
        bucket["count"] += 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile": cfg.profile,
        "config": asdict(cfg),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "pid": os.getpid(),
        },
        "elapsed_s": round(elapsed, 2),
        "overall": {
            "requests": len(records),
            "success": len(records) - len(errors),
            "failure": len(errors),
            "error_rate": round(len(errors) / len(records), 4) if records else 0,
            "server_error_rate": round(
                len(server_errors) / len(records), 4
            ) if records else 0,
            "rps": round(len(records) / elapsed, 1),
            **_latency_stats([r.latency_ms for r in records]),
        },
        "actions": actions,
        "errors": sorted(
            [{"key": k, **v} for k, v in error_buckets.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10],
    }


def _judge(summary: dict) -> list[dict]:
    overall = summary["overall"]
    checks = [
        {
            "name": "错误率 ≤ 1%",
            "actual": f"{overall['error_rate'] * 100:.2f}%",
            "pass": overall["error_rate"] <= THRESHOLDS["error_rate"],
        },
        {
            "name": "P95 ≤ 500ms",
            "actual": f"{overall['p95']}ms",
            "pass": overall["p95"] <= THRESHOLDS["p95_ms"],
        },
        {
            "name": "无 5xx",
            "actual": f"{overall['server_error_rate'] * 100:.2f}%",
            "pass": overall["server_error_rate"] <= THRESHOLDS["server_error_rate"],
        },
    ]
    return checks


def _bottleneck_hints(summary: dict) -> list[str]:
    """从结果里给出可解释的瓶颈线索，而不是只丢一张表。"""
    hints: list[str] = []
    errors = " ".join(item["key"] for item in summary["errors"])
    actions = summary["actions"]

    if "database is locked" in errors.lower():
        hints.append(
            "出现 `database is locked`：SQLite 是单写锁，写并发升高后会在数据库层排队，"
            "这是**被测服务的容量上限**，不是压测器的问题。生产应换成 PostgreSQL/MySQL 并单独压数据库。"
        )
    if "Timeout" in errors or "timed out" in errors:
        hints.append(
            "出现超时：检查线程池/连接池上限，以及同步调用下游（支付网关）是否拖住了请求。"
        )
    if actions.get("pay_order", {}).get("p95", 0) > 3 * max(
        actions.get("get_order", {}).get("p95", 1), 1
    ):
        hints.append(
            "`pay_order` 的 P95 明显高于查询接口：支付是同步串行调用外部网关，"
            "应关注网关超时设置、重试策略，以及是否该改成异步回调。"
        )
    if summary["overall"]["p95"] > 3 * max(summary["overall"]["avg"], 1):
        hints.append(
            "P95 远高于平均值：存在长尾请求，通常是锁等待、GC 或慢查询，需要看单请求耗时分布。"
        )
    if actions.get("create_order", {}).get("p95", 0) > THRESHOLDS["p95_ms"]:
        hints.append(
            "写接口 `create_order` 的 P95 超过阈值：本服务底层是 SQLite，**单写锁**会让并发写排队，"
            "这是当前部署形态的容量上限。判断方法：看 `timeseries.csv` 里 TPS 是否在某个并发点后不再上升。"
            "生产应使用 PostgreSQL/MySQL，或把写操作收敛到单队列。"
        )
    if not hints:
        hints.append("本次未发现明显异常，可按同一脚本提高并发继续找拐点。")
    return hints


def _write_timeseries(result: RunResult, path: Path) -> None:
    buckets: dict[int, list[Record]] = {}
    for record in result.records:
        bucket = int(record.ts - result.started_at)
        buckets.setdefault(bucket, []).append(record)

    lines = ["second,requests,errors,tps,avg_ms,p95_ms"]
    for second in sorted(buckets):
        items = buckets[second]
        latencies = sorted(r.latency_ms for r in items)
        errors = sum(1 for r in items if not r.ok)
        lines.append(
            f"{second},{len(items)},{errors},"
            f"{len(items)},{round(sum(latencies) / len(latencies), 1)},"
            f"{round(_percentile(latencies, 95), 1)}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_report(
    summary: dict,
    checks: list[dict],
    hints: list[str],
    result: RunResult,
    outdir: Path,
    previous: dict | None,
) -> None:
    overall = summary["overall"]
    cfg = summary["config"]
    lines = [
        "# 性能测试报告",
        "",
        f"- 场景：`{summary['profile']}`　并发：{cfg['users']}　持续：{cfg['duration']}s"
        f"　压测器：自研轻量 runner（requests + 线程）",
        f"- 被测服务：{cfg['base_url']}　环境：{summary['environment']['platform']}"
        f" / Python {summary['environment']['python']}",
        f"- 生成时间：{summary['generated_at']}",
        "",
        "## 1. 总览",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 总请求 | {overall['requests']} |",
        f"| 成功 / 失败 | {overall['success']} / {overall['failure']} |",
        f"| 错误率 | {overall['error_rate'] * 100:.2f}% |",
        f"| 实际 RPS | {overall['rps']} |",
        f"| 平均 / P50 | {overall['avg']} / {overall['p50']} ms |",
        f"| P90 / P95 / P99 | {overall['p90']} / {overall['p95']} / {overall['p99']} ms |",
        f"| 最大耗时 | {overall['max']} ms |",
        "",
        "## 2. 门禁判定",
        "",
        "| 标准 | 实测 | 结论 |",
        "|---|---|---|",
    ]
    for check in checks:
        lines.append(f"| {check['name']} | {check['actual']} | {'✅ 通过' if check['pass'] else '❌ 未通过'} |")

    lines += ["", "## 3. 分接口", "", "| 接口 | 请求数 | 失败 | 错误率 | 平均 | P95 | P99 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name, stats in sorted(summary["actions"].items(), key=lambda kv: -kv[1]["requests"]):
        lines.append(
            f"| {name} | {stats['requests']} | {stats['failure']} | "
            f"{stats['error_rate'] * 100:.2f}% | {stats['avg']}ms | "
            f"{stats['p95']}ms | {stats['p99']}ms |"
        )

    if summary["errors"]:
        lines += ["", "## 4. 错误分布", "", "| 次数 | 错误 |", "|---:|---|"]
        for item in summary["errors"]:
            lines.append(f"| {item['count']} | `{item['key'][:160]}` |")

    lines += ["", "## 5. 瓶颈线索", ""]
    lines += [f"- {hint}" for hint in hints]

    next_no = 6
    if previous:
        prev = previous["overall"]
        lines += [
            "",
            f"## {next_no}. 与上次同场景结果对比",
            "",
            "| 指标 | 上次 | 本次 | 变化 |",
            "|---|---:|---:|---:|",
            f"| RPS | {prev['rps']} | {overall['rps']} | {_delta(prev['rps'], overall['rps'])} |",
            f"| P95 | {prev['p95']}ms | {overall['p95']}ms | {_delta(prev['p95'], overall['p95'])} |",
            f"| 错误率 | {prev['error_rate'] * 100:.2f}% | {overall['error_rate'] * 100:.2f}% | — |",
        ]
        next_no += 1

    failed = [check["name"] for check in checks if not check["pass"]]
    conclusion = (
        "所有门禁通过，可按同一脚本继续提高并发找容量拐点。"
        if not failed
        else f"未通过：{('、'.join(failed))}。需先定位瓶颈，再用同一场景复测定论。"
    )
    lines += [
        "",
        f"## {next_no}. 结论与建议",
        "",
        f"- 结论：{conclusion}",
        "- 建议：",
        "  - 先看「瓶颈线索」和 `timeseries.csv` 的 TPS 曲线，确认是锁等待、下游阻塞还是线程池打满；",
        "  - 修复后**用同一 profile 重跑**，报告会自动和上一次对比，形成性能基线；",
        "  - 结论只写在报告里不算完，要能落到一个具体的优化项和负责人。",
        "",
        f"> 原始数据：`{outdir.name}/summary.json`、`{outdir.name}/timeseries.csv`",
    ]
    (outdir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _delta(previous: float, current: float) -> str:
    if not previous:
        return "—"
    change = (current - previous) / previous * 100
    return f"{change:+.1f}%"


def _load_previous(outdir: Path, profile: str) -> dict | None:
    candidates = sorted(
        (p for p in outdir.parent.glob(f"{profile}-*/summary.json") if p.parent != outdir),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    try:
        return json.loads(candidates[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def run(cfg: Config, outdir: Path | None = None) -> dict:
    outdir = outdir or Path(__file__).resolve().parent / "results" / (
        f"{cfg.profile}-{datetime.now():%Y%m%d-%H%M%S}"
    )
    outdir.mkdir(parents=True, exist_ok=True)

    result = RunResult()
    result.started_at = time.time()
    stop_at = result.started_at + cfg.duration

    users = [
        VirtualUser(i + 1, cfg, result, stop_at) for i in range(cfg.users)
    ]
    print(
        f"[loadgen] profile={cfg.profile} users={cfg.users} "
        f"duration={cfg.duration}s spawn={cfg.spawn_rate}/s -> {cfg.base_url}"
    )
    for user in users:
        user.start()
        if cfg.spawn_rate:
            time.sleep(1 / cfg.spawn_rate)

    for user in users:
        user.join(timeout=max(cfg.duration, 5) + 30)
    result.finished_at = time.time()

    summary = _summarize(result, cfg)
    checks = _judge(summary)
    hints = _bottleneck_hints(summary)
    previous = _load_previous(outdir, cfg.profile)

    payload = {**summary, "checks": checks, "hints": hints}
    (outdir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_timeseries(result, outdir / "timeseries.csv")
    _write_report(summary, checks, hints, result, outdir, previous)

    print(
        f"[loadgen] done: {summary['overall']['requests']} req, "
        f"{summary['overall']['rps']} rps, "
        f"p95={summary['overall']['p95']}ms, "
        f"err={summary['overall']['error_rate'] * 100:.2f}%"
    )
    print(f"[loadgen] report: {outdir / 'report.md'}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="订单服务轻量压测器")
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="smoke")
    parser.add_argument("--users", type=int)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--spawn-rate", type=float)
    parser.add_argument("--think-time", type=float)
    args = parser.parse_args(argv)

    profile = PROFILES[args.profile]
    cfg = Config(
        base_url=args.base_url,
        profile=args.profile,
        users=args.users or profile["users"],
        duration=args.duration or profile["duration"],
        spawn_rate=args.spawn_rate or profile["spawn_rate"],
        think_time=(
            args.think_time if args.think_time is not None else profile["think_time"]
        ),
    )
    summary = run(cfg)
    return 0 if all(check["pass"] for check in _judge(summary)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
