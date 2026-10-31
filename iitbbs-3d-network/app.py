import json, os, random, time, urllib.request
from flask import Flask, jsonify, send_from_directory, redirect, abort
import pydac_adapter

ROOT = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(ROOT, "static"), static_url_path="/static")
BUILDINGS = json.load(open(os.path.join(ROOT, "data", "buildings.json"), encoding="utf-8"))
BY_ID = {b["id"]: b for b in BUILDINGS}

# ---------- simulator (used when PyDAC is not connected) ----------
STATE = {}
LAST = 0.0

def _base(b):
    hostel = b["type"] == "hostel"
    aps = 24 if hostel else 12
    return dict(latency_ms=random.uniform(6, 18), loss_pct=random.uniform(0, .4),
                down_mbps=random.uniform(300, 900), up_mbps=random.uniform(120, 400),
                clients=random.randint(150, 480) if hostel else random.randint(10, 160),
                aps_online=aps, aps_total=aps, fault=0)

for b in BUILDINGS:
    STATE[b["id"]] = _base(b)

def _status(m):
    if m["aps_online"] == 0 or m["loss_pct"] > 6 or m["latency_ms"] > 120: return "down"
    if m["loss_pct"] > 1.5 or m["latency_ms"] > 50 or m["aps_online"] < m["aps_total"] * .8: return "warn"
    return "ok"

def _step():
    global LAST
    if time.time() - LAST < 1.2: return
    LAST = time.time()
    for b in BUILDINGS:
        m = STATE[b["id"]]
        if m["fault"] > 0:
            m["fault"] -= 1
            m["latency_ms"] += random.uniform(5, 25)
            m["loss_pct"] += random.uniform(.5, 2)
            if m["fault"] == 0: m["aps_online"] = m["aps_total"]
        else:
            m["latency_ms"] += (12 - m["latency_ms"]) * .25 + random.uniform(-2, 2)
            m["loss_pct"] += (.2 - m["loss_pct"]) * .3
            if random.random() < .006:   # random incident
                m["fault"] = random.randint(6, 18)
                m["aps_online"] = max(0, m["aps_total"] - random.randint(2, m["aps_total"]))
        m["latency_ms"] = max(2, m["latency_ms"]); m["loss_pct"] = max(0, m["loss_pct"])
        m["down_mbps"] = max(20, m["down_mbps"] + random.uniform(-40, 40))
        m["up_mbps"] = max(10, m["up_mbps"] + random.uniform(-20, 20))
        m["clients"] = max(0, m["clients"] + random.randint(-6, 6))

def snapshot():
    _step()
    out = {}
    for b in BUILDINGS:
        live = None
        try: live = pydac_adapter.read_block(b)
        except Exception: live = None
        m = dict(live) if live else {k: v for k, v in STATE[b["id"]].items() if k != "fault"}
        m = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in m.items()}
        m["status"] = _status(m)
        out[b["id"]] = m
    return out

# ---------- routes ----------
@app.get("/")
def index(): return send_from_directory(app.static_folder, "index.html")

@app.get("/diagnostics")
def diagnostics(): return send_from_directory(app.static_folder, "diagnostics.html")

@app.get("/api/buildings")
def api_buildings(): return jsonify(BUILDINGS)

@app.get("/api/network")
def api_network():
    return jsonify(dict(source="pydac" if pydac_adapter.HAVE_PYDAC else "simulated",
                        time=time.time(), blocks=snapshot()))

@app.post("/api/diagnose/<bid>")
def api_diagnose(bid):
    if bid not in BY_ID: abort(404)
    m = snapshot()[bid]
    bad = m["status"] == "down"; warn = m["status"] == "warn"
    steps = [
        ("Ping building gateway", not bad, f"{m['latency_ms']} ms"),
        ("Packet loss check", m["loss_pct"] < 1.5, f"{m['loss_pct']}% loss"),
        ("DHCP lease", not bad, "lease granted" if not bad else "no response"),
        ("DNS lookup", not bad, "resolved in 14 ms" if not bad else "timed out"),
        ("Access points online", m["aps_online"] >= m["aps_total"] * .8, f"{m['aps_online']} of {m['aps_total']}"),
        ("Throughput test", not (bad or warn), f"{m['down_mbps']} down / {m['up_mbps']} up Mbps"),
    ]
    time.sleep(.4)
    return jsonify([dict(step=s, ok=o, detail=d) for s, o, d in steps])

# three.js: served from static/vendor if present, otherwise downloaded once and cached
CDN = "https://cdn.jsdelivr.net/npm/three@0.160.0/"
VENDOR = os.path.join(ROOT, "static", "vendor")

@app.get("/vendor/<path:p>")
def vendor(p):
    rel = "build/three.module.js" if p == "three.module.js" else "examples/jsm/" + p.replace("addons/", "", 1)
    local = os.path.join(VENDOR, p)
    if not os.path.exists(local):
        try:
            os.makedirs(os.path.dirname(local), exist_ok=True)
            data = urllib.request.urlopen(CDN + rel, timeout=10).read()
            open(local, "wb").write(data)
        except Exception:
            return redirect(CDN + rel)
    return send_from_directory(VENDOR, p, mimetype="text/javascript")

if __name__ == "__main__":
    print("\n  IIT Bhubaneswar 3D network map ->  http://127.0.0.1:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
