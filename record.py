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
    if not pairs:
        return None
    best = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
    return best.get("priceUsd")

stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
rows = []
for line in open("watchlist.txt"):
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
    time.sleep(2)

with open("prices.csv", "a") as f:
    for r in rows:
        f.write(r + "\n")
