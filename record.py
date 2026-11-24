import time
import json
import urllib.request

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def price_of(address):
    data = get_json("https://api.dexscreener.com/latest/dex/search?q=" + address)
    pairs = [p for p in data.get("pairs", [])
             if p["baseToken"]["address"] == address and p.get("chainId") == "solana"]
    good = []
    for p in pairs:
        liq = (p.get("liquidity") or {}).get("usd") or 0
        if p.get("priceUsd") and liq >= 50000:
            good.append(float(p["priceUsd"]))
    if not good:
        return None
    good.sort()
    return "{:.15f}".format(good[(len(good) - 1) // 2])

def all_lines():
    out = []
    seen = set()
    for path in ("watchlist.txt", "auto_watchlist.txt", "paper_list.txt"):
        try:
            lines = open(path).readlines()
        except FileNotFoundError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) == 2 and parts[0] not in seen:
                seen.add(parts[0])
                out.append(line)
    return out

stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
rows = []
for line in all_lines():
    parts = line.split()
    if len(parts) != 2:
        continue
    addr, name = parts
    try:
        price = price_of(addr)
    except Exception as e:
        print(name, "error:", e)
        price = None
    if price:
        rows.append(f"{stamp},{name},{addr},{price}")
        print(stamp, name, price)
    else:
        print(stamp, name, "NO PRICE FOUND")
    time.sleep(2)

with open("prices.csv", "a") as f:
    for r in rows:
        f.write(r + "\n")
