import json
import time
import urllib.request

QUERIES = ["BONK", "JUP", "WIF", "PYTH", "RAY"]
CHAIN = "solana"
MIN_LIQUIDITY = 50000
MIN_VOLUME_24H = 20000
MIN_AGE_HOURS = 24
MIN_HOLDERS = 500
MAX_CHECKS = 15

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def scan():
    now_ms = time.time() * 1000
    best = {}
    for q in QUERIES:
        try:
            data = get_json("https://api.dexscreener.com/latest/dex/search?q=" + q)
        except Exception:
            continue
        for p in data.get("pairs", []):
            if p.get("chainId") != CHAIN:
                continue
            liq = (p.get("liquidity") or {}).get("usd") or 0
            vol = (p.get("volume") or {}).get("h24") or 0
            created = p.get("pairCreatedAt")
            age_h = (now_ms - created) / 3600000 if created else 0
            if liq < MIN_LIQUIDITY or vol < MIN_VOLUME_24H or age_h < MIN_AGE_HOURS:
                continue
            addr = p["baseToken"]["address"]
            if addr not in best or liq > best[addr]["liquidity"]:
                best[addr] = {"symbol": p["baseToken"]["symbol"], "address": addr,
                              "price": p.get("priceUsd"), "liquidity": liq}
        time.sleep(1)
    return sorted(best.values(), key=lambda x: x["liquidity"], reverse=True)

def security(addr):
    url = "https://api.gopluslabs.io/api/v1/solana/token_security?contract_addresses=" + addr
    return (get_json(url).get("result") or {}).get(addr)

def evaluate(info):
    if not info:
        return ["no security data"]
    reasons = []
    for key in ("mintable", "freezable", "closable", "balance_mutable_authority"):
        v = info.get(key)
        status = v.get("status") if isinstance(v, dict) else None
        if status != "0":
            reasons.append(key + " not off")
    for key in ("transfer_fee", "transfer_hook"):
        v = info.get(key)
        if v is None:
            reasons.append(key + " unknown")
        elif v:
            reasons.append(key + " present")
    if str(info.get("non_transferable")) != "0":
        reasons.append("non_transferable")
    try:
        holders = int(info.get("holder_count"))
        if holders < MIN_HOLDERS:
            reasons.append("only " + str(holders) + " holders")
    except (TypeError, ValueError):
        reasons.append("holder_count unknown")
    return reasons

out = []
for t in scan()[:MAX_CHECKS]:
    try:
        reasons = evaluate(security(t["address"]))
    except Exception as e:
        reasons = ["check failed"]
    t["verdict"] = "ACCEPT" if not reasons else "REJECT"
    t["reasons"] = reasons
    out.append(t)
    time.sleep(1.5)

with open("signals.json", "w") as f:
    json.dump({"updated": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "items": out}, f)
print(len(out), "tokens checked")
