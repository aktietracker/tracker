import json, asyncio, datetime as dt
import requests, aiohttp

STOCKS = {
    "ossdsign": ("962596", "OSSD.ST"),
    "smarteye": ("710675", "SEYE.ST"),
    "integrum": ("753680", "INTEG-B.ST"),
    "greenlandscaping": ("837354", "GREEN.ST"),
}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "application/json"}
START = "2026-08-04"
out = {"generated": dt.datetime.utcnow().isoformat(), "stocks": {}}

def summ(pts):
    since = [p for p in pts if p[0] >= START]
    return {"n": len(pts), "n_since_start": len(since), "first": pts[0] if pts else None,
            "last": pts[-1] if pts else None, "sample_since_start": since[:3]}

def avanza(oid):
    res = []
    for tp in ("three_months", "one_year"):
        url = f"https://www.avanza.se/_api/price-chart/stock/{oid}?timePeriod={tp}&resolution=day"
        info = {"url": url}
        try:
            r = requests.get(url, headers=UA, timeout=25)
            info["status"] = r.status_code
            try:
                j = r.json()
            except Exception:
                info["raw"] = r.text[:300]
                res.append(info)
                continue
            pts = []
            if isinstance(j, dict) and isinstance(j.get("ohlc"), list):
                for o in j["ohlc"]:
                    ts, cl = o.get("timestamp"), o.get("close")
                    if ts is not None and cl is not None:
                        pts.append((dt.datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d"), cl))
            if pts:
                info.update(summ(pts))
            else:
                info["raw"] = json.dumps(j, ensure_ascii=False)[:400]
        except Exception as e:
            info["error"] = str(e)[:200]
        res.append(info)
    return res

def yahoo(tk):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?range=6mo&interval=1d"
    info = {"url": url}
    try:
        r = requests.get(url, headers=UA, timeout=25)
        info["status"] = r.status_code
        j = r.json()
        res = j["chart"]["result"][0]
        ts = res["timestamp"]
        cl = res["indicators"]["quote"][0]["close"]
        pts = [(dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"), c) for t, c in zip(ts, cl) if c is not None]
        info.update(summ(pts))
        info["currency"] = res.get("meta", {}).get("currency")
    except Exception as e:
        info["error"] = str(e)[:200]
        try:
            info["raw"] = r.text[:300]
        except Exception:
            pass
    return info

for key, (oid, tk) in STOCKS.items():
    out["stocks"][key] = {"avanza_price_chart": avanza(oid), "yahoo": yahoo(tk)}

try:
    import pyavanza
    async def raw(oid):
        async with aiohttp.ClientSession() as s:
            return await pyavanza.get_stock_async(s, oid)
    d = asyncio.run(raw("962596"))
    out["pyavanza_ossdsign"] = {"historicalClosingPrices": d.get("historicalClosingPrices"), "quote": d.get("quote")}
except Exception as e:
    out["pyavanza_ossdsign"] = {"error": str(e)[:200]}

with open("probe_result.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2, default=str)
print("klar")
