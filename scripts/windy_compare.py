import json, math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
from weather_layers.series import decode_chunk

out = Path("data/out"); m = json.loads((out / "manifest.json").read_text()); s = m["series"]
lat, lon = 63 + 48/60 + 3/3600, 8.30
g = s["grid"]; r = math.floor((lat + 90) / g["dlat"]); c = math.floor((lon + 180) / g["dlon"])
cy, cx = r // 4, c // 4
arr = decode_chunk((out / s["template"].replace("{cy}", str(cy)).replace("{cx}", str(cx))).read_bytes())
names = [v["name"] for v in s["variables"]]
times = [datetime.fromisoformat(t.replace("Z", "+00:00")) for t in s["times"]]
def series(name):
    v = s["variables"][names.index(name)]
    codes = arr[names.index(name), r - cy*4, c - cx*4].astype(float)
    vals = v["offset"] + v["scale"] * codes; vals[codes == 255] = np.nan
    return vals
def src(name, t):
    v = s["variables"][names.index(name)]
    for seg in v["segments"]:
        if seg["start"] <= t.strftime("%Y-%m-%dT%H:%M:%SZ") <= seg["end"]:
            return seg["source"]
    return "-"
def at(name, t):
    vals = series(name); best = None
    for i, ti in enumerate(times):
        if not np.isnan(vals[i]) and abs((ti - t).total_seconds()) <= 1.5 * 3600:
            if best is None or abs((ti - t).total_seconds()) < abs((times[best] - t).total_seconds()): best = i
    return (vals[best], src(name, times[best])) if best is not None else (np.nan, "-")

windy = {
 "wind": "3 3 3 4 2 1 2 3 5 6 5 6 4 7 9 10 6 4 9 5 6 6 5 8 6 5 8 11 8 7 9 8 10 12 8 5 7 6 13 13",
 "gust": "5 6 5 6 6 4 4 5 8 8 8 8 8 9 12 15 13 9 12 11 10 8 9 10 11 9 11 15 14 10 13 14 13 15 15 10 9 10 16 19",
 "waves": "1 0.9 1.1 1.6 2.2 2.8 3.1 3.4 3.7 3.9 4 3.9 3.6 3.3 3.1 2.9 2.6 2.3 2.2 2 2 2.4 2.6 2.4 2.2 2.1 2.2 2.8 2.6 2.2 2.2 2.1 2.2 2.9 3.2 2.9 2.7 2.7 3.2 3.8",
 "swell": "0.8 0.7 0.9 1.4 2 2.6 2.9 3.2 3.5 3.7 2.8 3.7 3.5 3.2 3 2.7 2.5 2.3 2 1.9 1.3 2.2 1.8 2.3 2.1 2 2.1 2.2 2.4 2.2 2 1.9 2 2.3 3 2.8 2.6 2.6 2.3 2.3",
}
windy = {k: [float(x) for x in v.split()] for k, v in windy.items()}
t0 = datetime(2026, 11, 27, 0, tzinfo=timezone.utc)
rows = []
var = {"wind": "wind_speed", "gust": "wind_gust", "waves": "wave_height", "swell": "swell_height"}
print(f"point {lat:.4f},{lon:.4f}  series cell centre {-90+(r+.5)*g['dlat']:.4f},{-180+(c+.5)*g['dlon']:.4f}")
print("UTC          | wind ours/windy | gust ours/windy | waves ours/windy | swell ours/windy | sources")
diffs = {k: [] for k in windy}
for i in range(40):
    t = t0 + timedelta(hours=3 * i)
    vals = {k: at(var[k], t) for k in windy}
    line = f"{t:%a %d %H}Z   "
    for k in windy:
        o, w = vals[k][0], windy[k][i]
        line += f"| {o:5.1f} / {w:4.1f}     " if not np.isnan(o) else f"|   –   / {w:4.1f}     "
        if not np.isnan(o) and t >= datetime(2026,11,27,12,tzinfo=timezone.utc):
            diffs[k].append((o - w, vals[k][1]))
    line += "| " + ",".join(sorted({vals[k][1] for k in windy}))
    print(line)
print()
for k, d in diffs.items():
    for srcname in sorted({x[1] for x in d}):
        dd = np.array([x[0] for x in d if x[1] == srcname])
        print(f"{k:6} vs Windy ECMWF, ours from {srcname:6}: n={len(dd):2d} bias={dd.mean():+.2f} mean|diff|={np.abs(dd).mean():.2f} max={np.abs(dd).max():.2f}")
