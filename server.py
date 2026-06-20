import json
import math
import sys
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "stock_workflow.db"


SAMPLE_STOCKS = [
    {
        "code": "600519",
        "name": "贵州茅台",
        "industry": "食品饮料",
        "market": "沪市主板",
        "market_cap": 18500,
        "listing_years": 24,
        "is_st": False,
        "is_suspended": False,
        "revenue_growth": 18.2,
        "profit_growth": 19.1,
        "roe": 31.4,
        "debt_ratio": 17.6,
        "operating_cashflow": 1,
        "pe": 23.5,
        "pb": 8.9,
        "dividend_yield": 2.1,
        "ma_trend": 74,
        "momentum_20d": 4.8,
        "turnover_rate": 0.7,
        "capital_flow": 0.8,
        "risk_flags": [],
    },
    {
        "code": "000858",
        "name": "五粮液",
        "industry": "食品饮料",
        "market": "深市主板",
        "market_cap": 5200,
        "listing_years": 28,
        "is_st": False,
        "is_suspended": False,
        "revenue_growth": 11.6,
        "profit_growth": 13.4,
        "roe": 24.1,
        "debt_ratio": 22.8,
        "operating_cashflow": 1,
        "pe": 18.2,
        "pb": 4.4,
        "dividend_yield": 3.2,
        "ma_trend": 66,
        "momentum_20d": 2.1,
        "turnover_rate": 1.1,
        "capital_flow": 0.3,
        "risk_flags": [],
    },
    {
        "code": "300750",
        "name": "宁德时代",
        "industry": "电力设备",
        "market": "创业板",
        "market_cap": 9400,
        "listing_years": 8,
        "is_st": False,
        "is_suspended": False,
        "revenue_growth": 22.5,
        "profit_growth": 26.8,
        "roe": 20.6,
        "debt_ratio": 62.3,
        "operating_cashflow": 1,
        "pe": 21.7,
        "pb": 4.8,
        "dividend_yield": 1.1,
        "ma_trend": 81,
        "momentum_20d": 8.4,
        "turnover_rate": 1.9,
        "capital_flow": 1.2,
        "risk_flags": ["资产负债率偏高"],
    },
    {
        "code": "002594",
        "name": "比亚迪",
        "industry": "汽车",
        "market": "深市主板",
        "market_cap": 7600,
        "listing_years": 15,
        "is_st": False,
        "is_suspended": False,
        "revenue_growth": 28.9,
        "profit_growth": 34.2,
        "roe": 23.3,
        "debt_ratio": 68.1,
        "operating_cashflow": 1,
        "pe": 24.8,
        "pb": 5.2,
        "dividend_yield": 1.0,
        "ma_trend": 77,
        "momentum_20d": 6.6,
        "turnover_rate": 1.5,
        "capital_flow": 0.5,
        "risk_flags": ["资产负债率偏高"],
    },
    {
        "code": "601318",
        "name": "中国平安",
        "industry": "非银金融",
        "market": "沪市主板",
        "market_cap": 8700,
        "listing_years": 19,
        "is_st": False,
        "is_suspended": False,
        "revenue_growth": 5.8,
        "profit_growth": 8.2,
        "roe": 12.8,
        "debt_ratio": 82.4,
        "operating_cashflow": 1,
        "pe": 8.9,
        "pb": 0.9,
        "dividend_yield": 5.5,
        "ma_trend": 59,
        "momentum_20d": 1.4,
        "turnover_rate": 0.6,
        "capital_flow": 0.2,
        "risk_flags": ["金融行业杠杆较高"],
    },
    {
        "code": "600036",
        "name": "招商银行",
        "industry": "银行",
        "market": "沪市主板",
        "market_cap": 9200,
        "listing_years": 24,
        "is_st": False,
        "is_suspended": False,
        "revenue_growth": 4.4,
        "profit_growth": 6.7,
        "roe": 15.1,
        "debt_ratio": 91.5,
        "operating_cashflow": 1,
        "pe": 7.2,
        "pb": 0.8,
        "dividend_yield": 5.9,
        "ma_trend": 61,
        "momentum_20d": 1.9,
        "turnover_rate": 0.5,
        "capital_flow": 0.1,
        "risk_flags": ["银行业资产质量需跟踪"],
    },
    {
        "code": "688981",
        "name": "中芯国际",
        "industry": "电子",
        "market": "科创板",
        "market_cap": 4500,
        "listing_years": 6,
        "is_st": False,
        "is_suspended": False,
        "revenue_growth": 16.3,
        "profit_growth": 9.1,
        "roe": 7.6,
        "debt_ratio": 34.2,
        "operating_cashflow": 1,
        "pe": 42.5,
        "pb": 2.7,
        "dividend_yield": 0.3,
        "ma_trend": 72,
        "momentum_20d": 5.5,
        "turnover_rate": 2.1,
        "capital_flow": 0.9,
        "risk_flags": ["估值偏高"],
    },
    {
        "code": "600276",
        "name": "恒瑞医药",
        "industry": "医药生物",
        "market": "沪市主板",
        "market_cap": 3000,
        "listing_years": 26,
        "is_st": False,
        "is_suspended": False,
        "revenue_growth": 12.7,
        "profit_growth": 15.5,
        "roe": 13.8,
        "debt_ratio": 12.9,
        "operating_cashflow": 1,
        "pe": 31.4,
        "pb": 4.1,
        "dividend_yield": 0.8,
        "ma_trend": 69,
        "momentum_20d": 3.6,
        "turnover_rate": 1.0,
        "capital_flow": 0.4,
        "risk_flags": [],
    },
    {
        "code": "000333",
        "name": "美的集团",
        "industry": "家用电器",
        "market": "深市主板",
        "market_cap": 5100,
        "listing_years": 13,
        "is_st": False,
        "is_suspended": False,
        "revenue_growth": 9.4,
        "profit_growth": 12.2,
        "roe": 20.2,
        "debt_ratio": 58.6,
        "operating_cashflow": 1,
        "pe": 13.7,
        "pb": 2.9,
        "dividend_yield": 4.4,
        "ma_trend": 64,
        "momentum_20d": 2.9,
        "turnover_rate": 0.8,
        "capital_flow": 0.2,
        "risk_flags": [],
    },
    {
        "code": "600900",
        "name": "长江电力",
        "industry": "公用事业",
        "market": "沪市主板",
        "market_cap": 6800,
        "listing_years": 23,
        "is_st": False,
        "is_suspended": False,
        "revenue_growth": 7.1,
        "profit_growth": 10.8,
        "roe": 14.7,
        "debt_ratio": 55.3,
        "operating_cashflow": 1,
        "pe": 19.6,
        "pb": 3.1,
        "dividend_yield": 3.7,
        "ma_trend": 70,
        "momentum_20d": 3.3,
        "turnover_rate": 0.4,
        "capital_flow": 0.3,
        "risk_flags": [],
    },
    {
        "code": "002415",
        "name": "海康威视",
        "industry": "计算机",
        "market": "深市主板",
        "market_cap": 3300,
        "listing_years": 16,
        "is_st": False,
        "is_suspended": False,
        "revenue_growth": 8.8,
        "profit_growth": 6.1,
        "roe": 15.9,
        "debt_ratio": 42.1,
        "operating_cashflow": 1,
        "pe": 20.1,
        "pb": 3.3,
        "dividend_yield": 2.5,
        "ma_trend": 55,
        "momentum_20d": -1.2,
        "turnover_rate": 0.9,
        "capital_flow": -0.4,
        "risk_flags": ["趋势偏弱"],
    },
    {
        "code": "000651",
        "name": "格力电器",
        "industry": "家用电器",
        "market": "深市主板",
        "market_cap": 2300,
        "listing_years": 30,
        "is_st": False,
        "is_suspended": False,
        "revenue_growth": 4.6,
        "profit_growth": 5.4,
        "roe": 22.4,
        "debt_ratio": 60.2,
        "operating_cashflow": 1,
        "pe": 8.4,
        "pb": 1.8,
        "dividend_yield": 6.8,
        "ma_trend": 58,
        "momentum_20d": 0.7,
        "turnover_rate": 0.8,
        "capital_flow": -0.1,
        "risk_flags": ["成长性偏弱"],
    },
]


DEFAULT_WORKFLOW = {
    "id": "wf_quality_value",
    "name": "A股质量价值精选",
    "description": "偏向盈利质量、合理估值和中等以上趋势的 A 股候选池。",
    "market": "A股",
    "universe_config": {
        "boards": ["沪市主板", "深市主板", "创业板", "科创板"],
        "industries": [],
        "min_market_cap": 500,
        "min_listing_years": 3,
        "exclude_st": True,
        "exclude_suspended": True,
    },
    "filter_config": {
        "min_revenue_growth": 5,
        "min_profit_growth": 5,
        "min_roe": 8,
        "max_debt_ratio": 95,
        "max_pe": 45,
        "min_ma_trend": 50,
    },
    "score_config": {
        "growth": 0.22,
        "quality": 0.26,
        "valuation": 0.22,
        "trend": 0.18,
        "capital": 0.12,
    },
    "risk_config": {"risk_penalty_per_flag": 4},
    "schedule_config": {"enabled": False, "cron": "0 18 * * 1-5"},
    "status": "enabled",
}


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                market TEXT NOT NULL,
                universe_config TEXT NOT NULL,
                filter_config TEXT NOT NULL,
                score_config TEXT NOT NULL,
                risk_config TEXT NOT NULL,
                schedule_config TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workflow_runs (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                run_time TEXT NOT NULL,
                status TEXT NOT NULL,
                stock_count INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_scores (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                stock_name TEXT NOT NULL,
                industry TEXT NOT NULL,
                total_score REAL NOT NULL,
                growth_score REAL NOT NULL,
                quality_score REAL NOT NULL,
                valuation_score REAL NOT NULL,
                trend_score REAL NOT NULL,
                capital_score REAL NOT NULL,
                risk_score REAL NOT NULL,
                rank INTEGER NOT NULL,
                reasons TEXT NOT NULL,
                risks TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS watchlist (
                id TEXT PRIMARY KEY,
                stock_code TEXT NOT NULL UNIQUE,
                stock_name TEXT NOT NULL,
                tags TEXT NOT NULL,
                note TEXT NOT NULL,
                added_from_run_id TEXT,
                added_score REAL,
                current_score REAL,
                alert_config TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        exists = conn.execute("SELECT COUNT(*) AS total FROM workflows").fetchone()["total"]
        if not exists:
            stamp = now_iso()
            conn.execute(
                """
                INSERT INTO workflows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_WORKFLOW["id"],
                    DEFAULT_WORKFLOW["name"],
                    DEFAULT_WORKFLOW["description"],
                    DEFAULT_WORKFLOW["market"],
                    json.dumps(DEFAULT_WORKFLOW["universe_config"], ensure_ascii=False),
                    json.dumps(DEFAULT_WORKFLOW["filter_config"], ensure_ascii=False),
                    json.dumps(DEFAULT_WORKFLOW["score_config"], ensure_ascii=False),
                    json.dumps(DEFAULT_WORKFLOW["risk_config"], ensure_ascii=False),
                    json.dumps(DEFAULT_WORKFLOW["schedule_config"], ensure_ascii=False),
                    DEFAULT_WORKFLOW["status"],
                    stamp,
                    stamp,
                ),
            )


def row_to_workflow(row):
    item = dict(row)
    for key in ["universe_config", "filter_config", "score_config", "risk_config", "schedule_config"]:
        item[key] = json.loads(item[key])
    return item


def workflow_to_params(data):
    workflow = {**DEFAULT_WORKFLOW, **data}
    for key in ["universe_config", "filter_config", "score_config", "risk_config", "schedule_config"]:
        workflow[key] = {**DEFAULT_WORKFLOW[key], **data.get(key, {})}
    return workflow


def clamp(value, min_value=0, max_value=100):
    return max(min_value, min(max_value, value))


def score_stock(stock, workflow):
    growth = clamp(stock["revenue_growth"] * 1.4 + stock["profit_growth"] * 1.6)
    quality = clamp(stock["roe"] * 2.2 + (100 - stock["debt_ratio"]) * 0.35 + stock["operating_cashflow"] * 15)
    valuation = clamp(100 - stock["pe"] * 1.45 + stock["dividend_yield"] * 4 + (5 - min(stock["pb"], 5)) * 3)
    trend = clamp(stock["ma_trend"] * 0.75 + stock["momentum_20d"] * 3)
    capital = clamp(50 + stock["capital_flow"] * 18 + math.log(stock["turnover_rate"] + 1) * 18)
    risk_penalty = len(stock["risk_flags"]) * workflow["risk_config"].get("risk_penalty_per_flag", 4)
    weights = workflow["score_config"]
    total = (
        growth * weights["growth"]
        + quality * weights["quality"]
        + valuation * weights["valuation"]
        + trend * weights["trend"]
        + capital * weights["capital"]
        - risk_penalty
    )

    reasons = []
    if stock["roe"] >= 15:
        reasons.append(f"ROE {stock['roe']}%，盈利质量较好")
    if stock["profit_growth"] >= 10:
        reasons.append(f"净利润增长 {stock['profit_growth']}%，成长性达标")
    if stock["pe"] <= 20:
        reasons.append(f"PE {stock['pe']}，估值相对克制")
    if stock["ma_trend"] >= 65:
        reasons.append("均线趋势处于较强区间")
    if stock["dividend_yield"] >= 3:
        reasons.append(f"股息率 {stock['dividend_yield']}%，具备分红吸引力")
    if not reasons:
        reasons.append("综合条件满足当前 workflow")

    risks = list(stock["risk_flags"])
    if stock["debt_ratio"] > 70:
        risks.append(f"资产负债率 {stock['debt_ratio']}%，需关注杠杆")
    if stock["momentum_20d"] < 0:
        risks.append("近 20 日动量为负")
    if stock["pe"] > 35:
        risks.append("PE 高于 35，估值容错较低")
    if not risks:
        risks.append("暂无明显风险标签")

    return {
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "industry": stock["industry"],
        "total_score": round(clamp(total), 1),
        "growth_score": round(growth, 1),
        "quality_score": round(quality, 1),
        "valuation_score": round(valuation, 1),
        "trend_score": round(trend, 1),
        "capital_score": round(capital, 1),
        "risk_score": round(risk_penalty, 1),
        "reasons": reasons,
        "risks": risks,
    }


def passes_filters(stock, workflow):
    universe = workflow["universe_config"]
    filters = workflow["filter_config"]
    if universe["exclude_st"] and stock["is_st"]:
        return False
    if universe["exclude_suspended"] and stock["is_suspended"]:
        return False
    if stock["market"] not in universe["boards"]:
        return False
    if universe["industries"] and stock["industry"] not in universe["industries"]:
        return False
    if stock["market_cap"] < universe["min_market_cap"]:
        return False
    if stock["listing_years"] < universe["min_listing_years"]:
        return False
    if stock["revenue_growth"] < filters["min_revenue_growth"]:
        return False
    if stock["profit_growth"] < filters["min_profit_growth"]:
        return False
    if stock["roe"] < filters["min_roe"]:
        return False
    if stock["debt_ratio"] > filters["max_debt_ratio"]:
        return False
    if stock["pe"] > filters["max_pe"]:
        return False
    if stock["ma_trend"] < filters["min_ma_trend"]:
        return False
    return True


def get_workflow(workflow_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
    return row_to_workflow(row) if row else None


def run_workflow(workflow_id):
    workflow = get_workflow(workflow_id)
    if not workflow:
        return None
    started = time.perf_counter()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    run_time = now_iso()
    scores = [score_stock(stock, workflow) for stock in SAMPLE_STOCKS if passes_filters(stock, workflow)]
    scores.sort(key=lambda item: item["total_score"], reverse=True)
    for index, item in enumerate(scores, start=1):
        item["rank"] = index
    duration_ms = int((time.perf_counter() - started) * 1000)
    summary = {
        "message": f"本次从 {len(SAMPLE_STOCKS)} 只 A 股样例中筛出 {len(scores)} 只候选股票",
        "top_stock": scores[0]["stock_name"] if scores else None,
        "avg_score": round(sum(item["total_score"] for item in scores) / len(scores), 1) if scores else 0,
    }

    with connect() as conn:
        conn.execute(
            "INSERT INTO workflow_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                workflow_id,
                run_time,
                "success",
                len(scores),
                duration_ms,
                json.dumps(summary, ensure_ascii=False),
                run_time,
            ),
        )
        for item in scores:
            conn.execute(
                """
                INSERT INTO stock_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"score_{uuid.uuid4().hex[:12]}",
                    run_id,
                    item["stock_code"],
                    item["stock_name"],
                    item["industry"],
                    item["total_score"],
                    item["growth_score"],
                    item["quality_score"],
                    item["valuation_score"],
                    item["trend_score"],
                    item["capital_score"],
                    item["risk_score"],
                    item["rank"],
                    json.dumps(item["reasons"], ensure_ascii=False),
                    json.dumps(item["risks"], ensure_ascii=False),
                    run_time,
                ),
            )
    return {"run": get_run(run_id), "results": get_results(run_id)}


def get_run(run_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["summary"] = json.loads(item["summary"])
    return item


def get_results(run_id):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM stock_scores WHERE run_id = ? ORDER BY rank ASC", (run_id,)
        ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["reasons"] = json.loads(item["reasons"])
        item["risks"] = json.loads(item["risks"])
        results.append(item)
    return results


def latest_run():
    with connect() as conn:
        row = conn.execute("SELECT * FROM workflow_runs ORDER BY created_at DESC LIMIT 1").fetchone()
    return get_run(row["id"]) if row else None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/workflows":
            with connect() as conn:
                rows = conn.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall()
            return self.send_json([row_to_workflow(row) for row in rows])
        if path.startswith("/api/workflows/") and path.endswith("/runs"):
            workflow_id = path.split("/")[3]
            with connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM workflow_runs WHERE workflow_id = ? ORDER BY created_at DESC LIMIT 20",
                    (workflow_id,),
                ).fetchall()
            runs = []
            for row in rows:
                item = dict(row)
                item["summary"] = json.loads(item["summary"])
                runs.append(item)
            return self.send_json(runs)
        if path.startswith("/api/workflows/"):
            workflow_id = path.split("/")[3]
            workflow = get_workflow(workflow_id)
            return self.send_json(workflow if workflow else {"error": "workflow not found"}, 200 if workflow else 404)
        if path.startswith("/api/runs/") and path.endswith("/results"):
            run_id = path.split("/")[3]
            return self.send_json({"run": get_run(run_id), "results": get_results(run_id)})
        if path == "/api/latest":
            run = latest_run()
            return self.send_json({"run": run, "results": get_results(run["id"]) if run else []})
        if path == "/api/stocks":
            qs = parse_qs(parsed.query)
            keyword = qs.get("q", [""])[0]
            stocks = SAMPLE_STOCKS
            if keyword:
                stocks = [
                    stock
                    for stock in SAMPLE_STOCKS
                    if keyword in stock["code"] or keyword in stock["name"] or keyword in stock["industry"]
                ]
            return self.send_json(stocks)
        if path == "/api/watchlist":
            with connect() as conn:
                rows = conn.execute("SELECT * FROM watchlist ORDER BY created_at DESC").fetchall()
            items = []
            for row in rows:
                item = dict(row)
                item["tags"] = json.loads(item["tags"])
                item["alert_config"] = json.loads(item["alert_config"])
                items.append(item)
            return self.send_json(items)
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/workflows":
            data = workflow_to_params(self.read_json())
            data["id"] = f"wf_{uuid.uuid4().hex[:10]}"
            data["market"] = "A股"
            stamp = now_iso()
            with connect() as conn:
                conn.execute(
                    "INSERT INTO workflows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        data["id"],
                        data["name"],
                        data["description"],
                        data["market"],
                        json.dumps(data["universe_config"], ensure_ascii=False),
                        json.dumps(data["filter_config"], ensure_ascii=False),
                        json.dumps(data["score_config"], ensure_ascii=False),
                        json.dumps(data["risk_config"], ensure_ascii=False),
                        json.dumps(data["schedule_config"], ensure_ascii=False),
                        data.get("status", "enabled"),
                        stamp,
                        stamp,
                    ),
                )
            return self.send_json(get_workflow(data["id"]), 201)
        if path.startswith("/api/workflows/") and path.endswith("/run"):
            workflow_id = path.split("/")[3]
            result = run_workflow(workflow_id)
            return self.send_json(result if result else {"error": "workflow not found"}, 200 if result else 404)
        if path == "/api/watchlist":
            data = self.read_json()
            stamp = now_iso()
            item_id = f"watch_{uuid.uuid4().hex[:10]}"
            with connect() as conn:
                conn.execute(
                    """
                    INSERT INTO watchlist VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(stock_code) DO UPDATE SET
                        stock_name = excluded.stock_name,
                        tags = excluded.tags,
                        note = excluded.note,
                        added_from_run_id = excluded.added_from_run_id,
                        added_score = excluded.added_score,
                        current_score = excluded.current_score,
                        alert_config = excluded.alert_config,
                        updated_at = excluded.updated_at
                    """,
                    (
                        item_id,
                        data["stock_code"],
                        data["stock_name"],
                        json.dumps(data.get("tags", []), ensure_ascii=False),
                        data.get("note", ""),
                        data.get("added_from_run_id"),
                        data.get("added_score"),
                        data.get("current_score"),
                        json.dumps(data.get("alert_config", {"score_drop": 8, "risk_event": True}), ensure_ascii=False),
                        stamp,
                        stamp,
                    ),
                )
            return self.send_json({"ok": True})
        return self.send_json({"error": "not found"}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path
        if path.startswith("/api/workflows/"):
            workflow_id = path.split("/")[3]
            old = get_workflow(workflow_id)
            if not old:
                return self.send_json({"error": "workflow not found"}, 404)
            data = workflow_to_params({**old, **self.read_json()})
            stamp = now_iso()
            with connect() as conn:
                conn.execute(
                    """
                    UPDATE workflows
                    SET name = ?, description = ?, market = ?, universe_config = ?, filter_config = ?,
                        score_config = ?, risk_config = ?, schedule_config = ?, status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        data["name"],
                        data["description"],
                        "A股",
                        json.dumps(data["universe_config"], ensure_ascii=False),
                        json.dumps(data["filter_config"], ensure_ascii=False),
                        json.dumps(data["score_config"], ensure_ascii=False),
                        json.dumps(data["risk_config"], ensure_ascii=False),
                        json.dumps(data["schedule_config"], ensure_ascii=False),
                        data.get("status", "enabled"),
                        stamp,
                        workflow_id,
                    ),
                )
            return self.send_json(get_workflow(workflow_id))
        return self.send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/watchlist/"):
            stock_code = path.split("/")[-1]
            with connect() as conn:
                conn.execute("DELETE FROM watchlist WHERE stock_code = ?", (stock_code,))
            return self.send_json({"ok": True})
        return self.send_json({"error": "not found"}, 404)


if __name__ == "__main__":
    init_db()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"A股选股 Workflow MVP running at http://127.0.0.1:{port}")
    server.serve_forever()
