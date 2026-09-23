#!/usr/bin/env python3
"""每日更新台股資料，輸出 data/<代號>.json 給 index.html 讀取。

主要來源：FinMind 開放 API（免金鑰每小時 300 次；設定 FINMIND_TOKEN 可到 600 次）。
備援來源：證交所 STOCK_DAY（日K，僅上市）與 T86（最新一日三大法人，僅上市）。
只用 Python 標準函式庫，不需要 pip install。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("DATA_DIR") or ROOT / "data")   # 自有主機可用 DATA_DIR 指到網站目錄下的 data
TW = timezone(timedelta(hours=8))
FINMIND = "https://api.finmindtrade.com/api/v4/data"
TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()
KEEP_DAYS = 520          # 最多保留約兩年
FIRST_LOAD_DAYS = 400    # 新股票第一次抓多久的歷史
UA = {"User-Agent": "Mozilla/5.0 (stock-dashboard updater)"}


def get_json(url, params=None, headers=None, tries=3):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={**UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"讀取失敗 {url}: {last}")


def finmind(dataset, stock_id=None, start=None):
    params = {"dataset": dataset}
    if stock_id:
        params["data_id"] = stock_id
    if start:
        params["start_date"] = start
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else None
    res = get_json(FINMIND, params, headers)
    if res.get("status") != 200:
        raise RuntimeError(f"FinMind {dataset}: {res.get('msg')}")
    return res.get("data", [])


# ---------- 轉換（純函式，方便測試） ----------
def price_rows(data):
    out = []
    for r in data:
        o, h, l, c = r.get("open"), r.get("max"), r.get("min"), r.get("close")
        if not all(isinstance(x, (int, float)) and x > 0 for x in (o, h, l, c)):
            continue  # 當天沒有成交
        out.append([r["date"], o, h, l, c, int(r.get("Trading_Volume") or 0)])
    return out


def inst_rows(data):
    out = {}
    for r in data:
        net = int((r.get("buy") or 0) - (r.get("sell") or 0))
        name = r.get("name", "")
        f, t, d = out.setdefault(r["date"], [0, 0, 0])
        if name.startswith("Foreign"):
            f += net
        elif name.startswith("Investment"):
            t += net
        elif name.startswith("Dealer"):
            d += net
        out[r["date"]] = [f, t, d]
    return out


def adj_rows(data):
    """除權息還原係數：參考價 ÷ 除權息前收盤。"""
    out = []
    for r in data:
        before, ref = r.get("before_price"), r.get("reference_price")
        if before and ref and 0 < ref / before < 1:
            out.append({"before": r["date"], "f": round(ref / before, 6)})
    return out


def num(s):
    return float(str(s).replace(",", "").replace("+", ""))


def twse_price_rows(obj):
    f = obj["fields"]
    ix = {k: f.index(k) for k in ("日期", "成交股數", "開盤價", "最高價", "最低價", "收盤價")}
    out = []
    for r in obj.get("data", []):
        try:
            y, m, d = r[ix["日期"]].split("/")
            out.append([f"{int(y) + 1911}-{m}-{d}", num(r[ix["開盤價"]]), num(r[ix["最高價"]]),
                        num(r[ix["最低價"]]), num(r[ix["收盤價"]]), int(num(r[ix["成交股數"]]))])
        except ValueError:
            continue
    return out


def twse_inst_row(obj, stock_id):
    f = obj["fields"]
    row = next((r for r in obj.get("data", []) if r[0].strip() == stock_id), None)
    if not row:
        return None
    foreign = sum(int(num(row[i])) for i, k in enumerate(f) if k.startswith("外") and "買賣超股數" in k)
    trust = int(num(row[f.index("投信買賣超股數")]))
    dealer = int(num(row[f.index("自營商買賣超股數")]))
    dt = str(obj["date"])
    return f"{dt[:4]}-{dt[4:6]}-{dt[6:]}", [foreign, trust, dealer]


# ---------- 備援 ----------
def twse_fallback(stock_id, doc):
    today = datetime.now(TW).date()
    months = {today.replace(day=1), (today.replace(day=1) - timedelta(days=1)).replace(day=1)}
    rows = []
    for m in sorted(months):
        obj = get_json("https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY",
                       {"date": m.strftime("%Y%m%d"), "stockNo": stock_id, "response": "json"})
        if obj.get("stat") == "OK":
            rows += twse_price_rows(obj)
        time.sleep(3)
    inst = {}
    if rows:
        last = max(r[0] for r in rows)
        obj = get_json("https://www.twse.com.tw/rwd/zh/fund/T86",
                       {"date": last.replace("-", ""), "selectType": "ALLBUT0999", "response": "json"})
        if obj.get("stat") == "OK":
            got = twse_inst_row(obj, stock_id)
            if got:
                inst[got[0]] = got[1]
    return rows, inst


# ---------- 主流程 ----------
def update(stock_id, names):
    path = DATA / f"{stock_id}.json"
    doc = json.loads(path.read_text("utf-8")) if path.exists() else {"id": stock_id, "days": [], "inst": {}}
    before = json.dumps([doc.get("days"), doc.get("inst"), doc.get("adj")], sort_keys=True)

    if doc["days"]:
        start = (date.fromisoformat(doc["days"][-1][0]) - timedelta(days=10)).isoformat()
    else:
        start = (datetime.now(TW).date() - timedelta(days=FIRST_LOAD_DAYS)).isoformat()

    source = "FinMind"
    try:
        rows = price_rows(finmind("TaiwanStockPrice", stock_id, start))
        inst = inst_rows(finmind("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start))
    except Exception as e:  # noqa: BLE001
        print(f"  FinMind 失敗（{e}），改用證交所備援")
        source = "證交所"
        rows, inst = twse_fallback(stock_id, doc)

    merged = {r[0]: r for r in doc["days"]}
    merged.update({r[0]: r for r in rows})
    doc["days"] = [merged[k] for k in sorted(merged)][-KEEP_DAYS:]
    doc.setdefault("inst", {}).update(inst)
    first = doc["days"][0][0] if doc["days"] else ""
    doc["inst"] = {k: v for k, v in doc["inst"].items() if k >= first}

    try:  # 除權息還原係數；抓不到就沿用舊的
        adj = adj_rows(finmind("TaiwanStockDividendResult", stock_id, first or start))
        known = {a["before"] for a in adj}
        doc["adj"] = sorted(adj + [a for a in doc.get("adj", []) if a["before"] not in known],
                            key=lambda a: a["before"])
    except Exception as e:  # noqa: BLE001
        print(f"  除權息資料略過：{e}")

    doc["name"] = names.get(stock_id) or doc.get("name", "")
    after = json.dumps([doc.get("days"), doc.get("inst"), doc.get("adj")], sort_keys=True)
    if after == before:
        print(f"  {stock_id} 沒有新資料")
        return
    doc["updated"] = datetime.now(TW).isoformat(timespec="minutes")
    doc["source"] = source
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"  {stock_id} {doc['name']} 已更新到 {doc['days'][-1][0]}，共 {len(doc['days'])} 天（{source}）")


def main():
    DATA.mkdir(exist_ok=True)
    ids = [s.strip().upper() for s in (ROOT / "stocks.txt").read_text("utf-8").split() if s.strip()]
    names = {}
    try:
        names = {r["stock_id"]: r["stock_name"] for r in finmind("TaiwanStockInfo")}
    except Exception as e:  # noqa: BLE001
        print(f"股票名稱略過：{e}")
    failed = 0
    for sid in ids:
        print(f"更新 {sid}")
        try:
            update(sid, names)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  {sid} 失敗：{e}")
        time.sleep(1)
    (DATA / "index.json").write_text(json.dumps({"stocks": ids}, ensure_ascii=False), "utf-8")
    if failed == len(ids):
        sys.exit(1)


if __name__ == "__main__":
    main()
