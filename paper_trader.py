import calendar
import json
import os
import sys
import time

WINDOW = 24
DIP = 0.03
TAKE = 0.04
STOP = 0.03
COST = 0.01
SIZE = 0.10
CASH0 = 1000.0

def read_list(path):
    items = []
    try:
        for line in open(path):
            parts = line.split()
            if len(parts) == 2:
                items.append((parts[0], parts[1]))
    except FileNotFoundError:
        pass
    return items

def load_prices():
    out = {}
    try:
        with open("prices.csv") as f:
            for line in f:
                p = line.strip().split(",")
                if len(p) != 4:
                    continue
                try:
                    ts = calendar.timegm(time.strptime(p[0], "%Y-%m-%d %H:%M:%S"))
                    out.setdefault(p[2], []).append((ts, float(p[3])))
                except ValueError:
                    continue
    except FileNotFoundError:
        pass
    return out

def load_history(addr):
    pts = {}
    last_hist = 0
    try:
        with open("history/" + addr + ".csv") as f:
            next(f, None)
            for line in f:
                p = line.strip().split(",")
                if len(p) >= 5:
                    try:
                        ts = int(p[0])
                        pts[ts] = float(p[4])
                        last_hist = max(last_hist, ts)
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    return pts, last_hist

def simulate(series, joins):
    events = []
    for addr, pts in series.items():
        for ts, p in pts:
            events.append((ts, addr, p))
    events.sort()
    cash = CASH0
    pos = {}
    last = {}
    win = {}
    first_p = {}
    trades = []
    curve = []
    exp_sum = 0.0
    exp_n = 0
    for ts, addr, p in events:
        w = win.setdefault(addr, [])
        last[addr] = p
        if ts > joins.get(addr, 0) and len(w) >= WINDOW:
            if addr not in first_p:
                first_p[addr] = p
            avg = sum(w[-WINDOW:]) / WINDOW
            if addr in pos:
                qty, entry, spend, ts_in = pos[addr]
                reason = None
                if p >= entry * (1 + TAKE):
                    reason = "take profit"
                elif p <= entry * (1 - STOP):
                    reason = "stop loss"
                if reason:
                    proceeds = qty * p * (1 - COST)
                    cash += proceeds
                    trades.append({"ts": ts, "addr": addr, "in": entry, "out": p, "pct": round((proceeds / spend - 1) * 100, 2), "reason": reason})
                    del pos[addr]
            elif p <= avg * (1 - DIP):
                equity_now = cash + sum(q[0] * last.get(a, q[1]) for a, q in pos.items())
                spend = min(equity_now * SIZE, cash)
                if spend > 0:
                    qty = spend * (1 - COST) / p
                    cash -= spend
                    pos[addr] = (qty, p, spend, ts)
        w.append(p)
        invested = sum(q[0] * last.get(a, q[1]) for a, q in pos.items())
        equity = cash + invested
        curve.append((ts, equity))
        exp_sum += invested / equity if equity > 0 else 0
        exp_n += 1
    return trades, pos, curve, last, first_p, exp_sum, exp_n

for _f in ("paper_state.json", "paper_forward.json", "paper_replay.json"):
    if not os.path.exists(_f):
        with open(_f, "w") as _h:
            _h.write("{}")

mode = sys.argv[1] if len(sys.argv) > 1 else "forward"
plist = read_list("paper_list.txt")
names = {a: n for a, n in plist}
tokens = [a for a, n in plist]
if not tokens:
    print("paper_list.txt is empty. Promote a token first.")
    sys.exit(0)

state = {}
if mode == "forward":
    try:
        state = json.load(open("paper_state.json"))
    except Exception:
        state = {}
    now = int(time.time())
    for a in tokens:
        if a not in state:
            state[a] = now
    with open("paper_state.json", "w") as f:
        json.dump(state, f)
joins = state if mode == "forward" else {}

live = load_prices()
series = {}
for addr in tokens:
    pts, last_hist = load_history(addr)
    for ts, p in live.get(addr, []):
        if ts > last_hist + 3600:
            pts[ts] = p
    if pts:
        series[addr] = sorted(pts.items())

trades, pos, curve, last, first_p, exp_sum, exp_n = simulate(series, joins)
out_name = "paper_" + mode + ".json"
if not curve or not first_p:
    with open(out_name, "w") as f:
        json.dump({"mode": mode, "message": "not enough data yet"}, f)
    print("Not enough data yet (each token needs", WINDOW, "price points)")
    sys.exit(0)

equity_end = curve[-1][1]
ret = (equity_end / CASH0 - 1) * 100
holds = [(last[a] / fp - 1 - 2 * COST) * 100 for a, fp in first_p.items()]
hold_avg = sum(holds) / len(holds)
exposure = exp_sum / exp_n if exp_n else 0.0
peak = 0.0
mdd = 0.0
for ts, eq in curve:
    peak = max(peak, eq)
    if peak > 0:
        mdd = max(mdd, (peak - eq) / peak * 100)
wins = len([t for t in trades if t["pct"] > 0])
mid = len(curve) // 2
half1 = (curve[mid][1] / curve[0][1] - 1) * 100 if curve[0][1] else 0
half2 = (curve[-1][1] / curve[mid][1] - 1) * 100 if curve[mid][1] else 0
days = (curve[-1][0] - curve[0][0]) / 86400.0
hold_scaled = hold_avg * exposure

for t in trades:
    t["name"] = names.get(t["addr"], t["addr"])
openp = []
for a, q in pos.items():
    openp.append({"name": names.get(a, a), "entry": q[1], "now": last[a], "pct": round((last[a] / q[1] - 1) * 100, 2)})
step = max(1, len(curve) // 150)

result = {
    "mode": mode,
    "updated": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
    "tokens": len(first_p),
    "days": round(days, 1),
    "trades": len(trades),
    "wins": wins,
    "return_pct": round(ret, 2),
    "hold_avg_pct": round(hold_avg, 2),
    "hold_scaled_pct": round(hold_scaled, 2),
    "exposure_pct": round(exposure * 100, 1),
    "max_drawdown_pct": round(mdd, 1),
    "half1_pct": round(half1, 2),
    "half2_pct": round(half2, 2),
    "stop_rule": {
        "four_weeks": days >= 28,
        "thirty_trades": len(trades) >= 30,
        "beats_holding": ret > hold_scaled,
        "drawdown_under_20": mdd < 20,
        "both_halves_positive": half1 > 0 and half2 > 0,
    },
    "open": openp,
    "recent_trades": trades[-40:],
    "curve": [[c[0], round(c[1], 2)] for c in curve[::step]],
}
with open(out_name, "w") as f:
    json.dump(result, f)
print(mode, "| days", round(days, 1), "| trades", len(trades), "| wins", wins, "| return", round(ret, 2), "% | hold", round(hold_scaled, 2), "% | drawdown", round(mdd, 1), "%")
