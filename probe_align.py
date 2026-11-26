import json, datetime as dt, requests
TICK = {"ossdsign": "OSSD.ST", "smarteye": "SEYE.ST", "integrum": "INTEG-B.ST", "greenlandscaping": "GREEN.ST"}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
out = {}
for key, tk in TICK.items():
    av = {r["date"]: r["close"] for r in json.load(open(f"data/price_{key}.json"))}
    j = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?range=6mo&interval=1d", headers=UA, timeout=25).json()
    res = j["chart"]["result"][0]
    yh = {}
    for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
        if c is not None:
            yh[dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")] = c
    ydays = sorted(d for d in yh if d >= "2026-08-04")
    adays = sorted(av)
    def close(a, b): return abs(a - b) / b < 0.005
    m0 = sum(1 for d in adays if d in yh and close(av[d], yh[d]))
    mp = sum(1 for i, d in enumerate(ydays[:-1]) if d in av and close(av[d], yh[ydays[i + 1]]))
    mm = sum(1 for i, d in enumerate(ydays[1:], 1) if d in av and close(av[d], yh[ydays[i - 1]]))
    out[key] = {"avanza_dagar": len(adays), "yahoo_dagar": len(ydays), "samma_datum": m0, "avanza_ligger_1_dag_fore": mp, "avanza_ligger_1_dag_efter": mm,
                "saknas_hos_yahoo": [d for d in adays if d not in yh][:5], "saknas_hos_avanza": [d for d in ydays if d not in av][:5]}
json.dump(out, open("probe_result.json", "w"), ensure_ascii=False, indent=2)
