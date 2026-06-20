"""
A股股票数据API连接测试脚本
逐一测试所有公开接口和Python库的可用性
"""

import sys
import time
import traceback

# ─────────────────────────────────────
# 辅助
# ─────────────────────────────────────

def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def ok(msg):
    print(f"  ✅ 成功: {msg}")

def fail(msg, err=None):
    print(f"  ❌ 失败: {msg}")
    if err:
        print(f"     错误: {err}")

# ═══════════════════════════════════════════
# 一、Python 开源库
# ═══════════════════════════════════════════

def test_akshare():
    header("1. AKShare (pip install akshare)")
    try:
        import akshare as ak
        print(f"     版本: {ak.__version__}")
        # 测试获取沪深300成分股
        df = ak.index_stock_cons(symbol="000300")
        ok(f"获取沪深300成分股，共 {len(df)} 条")
        print(f"     前3条: {df.head(3).to_string(index=False)}")
    except Exception as e:
        fail("AKShare 连接/调用失败", str(e)[:200])

def test_baostock():
    header("2. Baostock (pip install baostock)")
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code == '0':
            ok(f"Baostock 登录成功")
            # 查询平安银行日K线
            rs = bs.query_history_k_data_plus("sh.000001", "date,open,high,low,close,volume",
                                              start_date='2025-01-01', end_date='2025-01-10')
            rows = []
            while rs.error_code == '0' and rs.next():
                rows.append(rs.get_row_data())
            ok(f"查询上证指数日K线，获取 {len(rows)} 条")
            if rows:
                print(f"     示例: {rows[0]}")
            bs.logout()
        else:
            fail(f"Baostock 登录失败", lg.error_msg)
    except Exception as e:
        fail("Baostock 连接/调用失败", str(e)[:200])

def test_tushare():
    header("3. Tushare (pip install tushare)")
    try:
        import tushare as ts
        print(f"     版本: {ts.__version__}")
        # Tushare需要token，用免token接口试试
        # ts.get_k_data() 不需要token
        df = ts.get_k_data("000001", start="2025-01-01", end="2025-01-10")
        if df is not None and len(df) > 0:
            ok(f"免token接口获取平安银行日K线，{len(df)} 条")
            print(f"     示例: {df.head(1).to_string(index=False)}")
        else:
            fail("Tushare 返回空数据")
    except Exception as e:
        fail("Tushare 连接/调用失败", str(e)[:200])

def test_efinance():
    header("4. efinance (pip install efinance)")
    try:
        import efinance as ef
        # 测试获取股票实时行情
        df = ef.stock.get_realtime_quotes()
        if df is not None and len(df) > 0:
            ok(f"获取A股实时行情，共 {len(df)} 条")
            print(f"     前3条: {df.head(3).to_string(index=False)}")
        else:
            fail("efinance 返回空数据")
    except Exception as e:
        fail("efinance 连接/调用失败", str(e)[:200])

def test_adata():
    header("5. AData (pip install adata)")
    try:
        import adata
        print(f"     版本: {adata.__version__}")
        # 测试获取A股实时行情
        df = adata.stock.market.get_market(stock_code='000001', start_date='2025-06-01', end_date='2025-06-20', k_type=1)
        if df is not None and len(df) > 0:
            ok(f"获取平安银行日K线，{len(df)} 条")
            print(f"     示例: {df.head(1).to_string(index=False)}")
        else:
            fail("AData 返回空数据")
    except Exception as e:
        fail("AData 连接/调用失败", str(e)[:200])

# ═══════════════════════════════════════════
# 二、公开 HTTP 接口
# ═══════════════════════════════════════════

def test_sina_api():
    header("6. 新浪财经 API")
    try:
        import requests
        # 新浪实时行情接口 - 查询平安银行(000001)和上证指数(sh000001)
        url = "https://hq.sinajs.cn/list=sh000001,sz000001"
        headers = {"Referer": "https://finance.sina.com.cn"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = 'gbk'
        if resp.status_code == 200 and len(resp.text) > 50:
            ok(f"新浪财经接口正常，状态码 {resp.status_code}")
            for line in resp.text.strip().split('\n'):
                print(f"     {line[:100]}")
        else:
            fail(f"新浪财经接口异常", f"状态码={resp.status_code}, 长度={len(resp.text)}")
    except Exception as e:
        fail("新浪财经连接失败", str(e)[:200])

def test_tencent_api():
    header("7. 腾讯证券接口")
    try:
        import requests
        # 腾讯实时行情接口
        url = "https://qt.gtimg.cn/q=sh000001,sz000001"
        headers = {"Referer": "https://gu.qq.com/"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = 'gbk'
        if resp.status_code == 200 and len(resp.text) > 50:
            ok(f"腾讯证券接口正常，状态码 {resp.status_code}")
            for line in resp.text.strip().split('\n')[:3]:
                print(f"     {line[:120]}")
        else:
            fail(f"腾讯证券接口异常", f"状态码={resp.status_code}")
    except Exception as e:
        fail("腾讯证券连接失败", str(e)[:200])

def test_eastmoney_api():
    header("8. 东方财富接口")
    try:
        import requests
        # 东方财富 - 涨停板数据接口
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1", "pz": "3", "po": "1", "np": "1",
            "fltt": "2", "invt": "2",
            "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f4,f5,f12,f14"
        }
        headers = {"Referer": "https://quote.eastmoney.com/"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data") and data["data"].get("diff"):
                items = data["data"]["diff"][:3]
                ok(f"东方财富接口正常，返回 {len(items)} 条")
                for item in items:
                    print(f"     {item.get('f14','?')}: 涨跌幅={item.get('f3','?')}% 现价={item.get('f2','?')}")
            else:
                fail("东方财富返回数据为空")
        else:
            fail(f"东方财富接口异常", f"状态码={resp.status_code}")
    except Exception as e:
        fail("东方财富连接失败", str(e)[:200])

def test_ths_api():
    header("9. 同花顺 SuperMind 接口")
    try:
        import requests
        # 同花顺 iFinD 公开接口 - 尝试获取板块资金流向
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPT_DMSK_TS_STOCKNEW",
            "columns": "SECURITY_CODE,SECURITY_NAME_ABBR,CHANGE_RATE",
            "filter": '(SECURITY_TYPE_CODE in ("058001001","058001008"))',
            "pageNumber": 1, "pageSize": 3,
            "sortTypes": -1, "sortColumns": "CHANGE_RATE",
            "source": "HSF10", "client": "WEB"
        }
        headers = {"Referer": "https://www.10jqka.com.cn/"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("result") and data["result"].get("data"):
                items = data["result"]["data"][:3]
                ok(f"同花顺接口正常，返回 {len(items)} 条")
                for item in items:
                    print(f"     {item}")
            else:
                fail("同花顺返回数据为空", str(data.get("message", ""))[:100])
        else:
            fail(f"同花顺接口异常", f"状态码={resp.status_code}")
    except Exception as e:
        fail("同花顺连接失败", str(e)[:200])


# ═══════════════════════════════════════════
# 额外测试：QMT / xtquant
# ═══════════════════════════════════════════

def test_xtquant():
    header("10. xtquant (QMT量化接口)")
    try:
        from xtquant import xtdata
        ok("xtquant 导入成功（已安装QMT客户端）")
        # 尝试获取数据
        data = xtdata.get_market_data(['000001.SZ'], count=3)
        ok(f"xtquant 获取平安银行数据成功")
    except ImportError:
        fail("xtquant 未安装", "需要安装 QMT 客户端（迅投）后才有此库")
    except Exception as e:
        fail("xtquant 连接失败", str(e)[:200])

# ─────────────────────────────────────
# 主流程
# ─────────────────────────────────────

if __name__ == "__main__":
    print("🚀 A股股票数据API连接测试")
    print(f"   测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Python: {sys.version}")

    results = {}

    # Python 开源库
    for name, fn in [
        ("AKShare", test_akshare),
        ("Baostock", test_baostock),
        ("Tushare", test_tushare),
        ("efinance", test_efinance),
        ("AData", test_adata),
    ]:
        try:
            fn()
            results[name] = "✅"
        except Exception as e:
            results[name] = "❌"
        time.sleep(1)  # 避免请求过快

    # HTTP 接口
    for name, fn in [
        ("新浪财经", test_sina_api),
        ("腾讯证券", test_tencent_api),
        ("东方财富", test_eastmoney_api),
        ("同花顺", test_ths_api),
    ]:
        try:
            fn()
            results[name] = "✅"
        except Exception as e:
            results[name] = "❌"
        time.sleep(1)

    # QMT
    try:
        test_xtquant()
        results["xtquant"] = "✅"
    except:
        results["xtquant"] = "❌"

    # 汇总
    header("📊 测试结果汇总")
    success = sum(1 for v in results.values() if v == "✅")
    total = len(results)
    print(f"\n   总计: {success}/{total} 通过\n")
    for name, status in results.items():
        print(f"   {status} {name}")
    print()
