import json
import os
import time
import urllib.request

QUERIES = ["BONK", "JUP", "WIF", "PYTH", "RAY"]
for _line in open("watchlist.txt"):
    _parts = _line.split()
    if len(_parts) == 2:
        QUERIES.append(_parts[0])
CHAIN = "solana"
MIN_LIQUIDITY = 50000
MIN_VOLUME_24H = 20000
MIN_AGE_HOURS = 24
MIN_HOLDERS = 500
MAX_CHECKS = 25

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
            if len(q) > 30 and p["baseToken"]["address"] != q:
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
    for attempt in range(3):
        try:
            result = (get_json(url).get("result") or {}).get(addr)
            if result:
                return result
        except Exception:
            pass
        time.sleep(10)
    return None

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

RUGCHECK_MAX_RISK = 60
JUP_MIN_ORGANIC = 40
JUP_REQUIRE_VERIFIED = True
GT_MIN_SCORE = 40

def fetch(url, headers=None, tries=3, wait=5):
    h = {"User-Agent": "Mozilla/5.0"}
    if headers:
        h.update(headers)
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception:
            time.sleep(wait)
    return None

def check_rugcheck(addr):
    data = fetch("https://api.rugcheck.xyz/v1/tokens/" + addr + "/report/summary")
    if not data or "score_normalised" not in data:
        return None
    out = []
    score = data.get("score_normalised")
    if isinstance(score, (int, float)) and score >= RUGCHECK_MAX_RISK:
        out.append("RugCheck risk score " + str(score))
    if data.get("rugged"):
        out.append("RugCheck says rugged")
    return out

def check_jupiter(addr):
    key = os.environ.get("JUPITER_API_KEY", "")
    if not key:
        return None
    data = fetch("https://api.jup.ag/tokens/v2/search?query=" + addr, {"x-api-key": key})
    if not isinstance(data, list):
        return None
    item = None
    for d in data:
        if d.get("id") == addr:
            item = d
    if item is None:
        return ["not found on Jupiter"]
    out = []
    audit = item.get("audit") or {}
    if audit.get("isSus"):
        out.append("Jupiter flags suspicious")
    organic = item.get("organicScore")
    if organic is not None and organic < JUP_MIN_ORGANIC:
        out.append("Jupiter organic score " + str(round(organic)))
    if JUP_REQUIRE_VERIFIED and not item.get("isVerified"):
        out.append("not verified on Jupiter")
    return out

def check_gecko(addr):
    data = fetch("https://api.geckoterminal.com/api/v2/networks/solana/tokens/" + addr + "/info")
    if not data or "data" not in data:
        return None
    attrs = (data.get("data") or {}).get("attributes") or {}
    out = []
    gt = attrs.get("gt_score")
    if gt is not None and gt < GT_MIN_SCORE:
        out.append("GeckoTerminal trust score " + str(round(gt)))
    if not attrs.get("websites") and not attrs.get("twitter_handle"):
        out.append("no website or X account listed")
    return out

def extra_checks(addr):
    reasons = []
    answered = []
    for name, fn in (("RugCheck", check_rugcheck), ("Jupiter", check_jupiter), ("GeckoTerminal", check_gecko)):
        try:
            result = fn(addr)
        except Exception:
            result = None
        if result is None:
            continue
        answered.append(name)
        reasons += result
        time.sleep(2)
    return reasons, answered

out = []
for t in scan()[:MAX_CHECKS]:
    addr = t["address"]
    reasons = []
    answered = []
    try:
        gp = security(addr)
        reasons += evaluate(gp)
        if gp:
            answered.append("GoPlus")
    except Exception:
        reasons.append("GoPlus check failed")
    extra_reasons, extra_answered = extra_checks(addr)
    reasons += extra_reasons
    answered += extra_answered
    if len(extra_answered) < 2:
        reasons.append("fewer than 2 extra sources answered")
    t["verdict"] = "ACCEPT" if not reasons else "REJECT"
    t["reasons"] = reasons
    t["checked_by"] = answered
    out.append(t)
    print(t["symbol"], t["verdict"], answered, reasons)
    time.sleep(8)

with open("signals.json", "w") as f:
    json.dump({"updated": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "items": out}, f)
print(len(out), "tokens checked")
