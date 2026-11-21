#!/usr/bin/env python3
"""Draw the contribution grid and monthly bar cards for the profile README.

Reads data/contributions.json (list of {date, count, level}). When GITHUB_TOKEN
is set, it first refreshes that file from the GitHub GraphQL API. Output goes
to cards/heatmap.svg and cards/activity.svg. STATIC=1 draws the final frame.
"""
import json
import os
import urllib.request
from collections import OrderedDict
from datetime import date, timedelta
from pathlib import Path

USER = os.environ.get("PROFILE_USERNAME", "salman-cc")
DATA = Path("data/contributions.json")
OUT = Path("cards")
STATIC = os.environ.get("STATIC") == "1"

BLUE, INK, MUTE, BG, LINE = "#2f5bea", "#14181f", "#5b6270", "#f6f1e7", "#d9d2c3"
SERIF = "font-family:'Instrument Serif','Iowan Old Style','Palatino Linotype',Palatino,Georgia,'Times New Roman',serif"
SANS = "font-family:'Segoe UI','Noto Sans','Helvetica Neue',Arial,sans-serif"
MONO = "font-family:'JetBrains Mono','DejaVu Sans Mono',Consolas,monospace"
SHADES = ["#e4dfd2", "#bcc9f5", "#8aa3f0", "#5a7eec", "#2f5bea"]

QUERY = """query($login:String!,$from:DateTime!,$to:DateTime!){user(login:$login){
contributionsCollection(from:$from,to:$to){contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"""

CSS = """
@keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
@keyframes pop{0%{opacity:0;transform:scale(.4)}100%{opacity:1;transform:scale(1)}}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
.a{opacity:0;animation:rise .7s cubic-bezier(.2,.8,.2,1) forwards}
.c{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .35s ease-out forwards}
.b{transform-box:fill-box;transform-origin:bottom;transform:scaleY(0);animation:grow .7s cubic-bezier(.2,.8,.2,1) forwards}
@media (prefers-reduced-motion:reduce){*{animation:none!important;opacity:1!important;transform:none!important}}
"""
if STATIC:
    CSS += "*{animation:none!important;opacity:1!important;transform:none!important}"


def level(count, top):
    if count <= 0:
        return 0
    return min(4, 1 + int(3 * (count - 1) / max(1, top - 1))) if top > 1 else 1


def refresh():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return
    end = date.today()
    start = end - timedelta(days=364)
    body = json.dumps({"query": QUERY, "variables": {
        "login": USER, "from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", body, {
        "Authorization": f"bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [{"date": d["date"], "count": d["contributionCount"]} for w in weeks for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(days))


def svg(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<style>{CSS}</style><rect width="{w}" height="{h}" rx="16" fill="{BG}"/>'
            f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="16" fill="none" stroke="{LINE}"/>{body}</svg>')


def heatmap(days, total, top):
    first = date.fromisoformat(days[0]["date"])
    pad = (first.weekday() + 1) % 7  # Sunday first
    cell, gap, x0, y0 = 11, 3, 28, 70
    parts = [
        f'<g class="a"><text x="28" y="40" style="{SERIF};font-size:30px" fill="{INK}">Every day, <tspan font-style="italic" fill="{BLUE}">in blue</tspan></text></g>',
        f'<text x="802" y="40" text-anchor="end" style="{MONO};font-size:12px" fill="{MUTE}">{total} contributions in the last year</text>',
    ]
    for i, d in enumerate(days):
        idx = i + pad
        wk, dow = divmod(idx, 7)
        x, y = x0 + wk * (cell + gap), y0 + dow * (cell + gap)
        lv = level(d["count"], top)
        delay = round(0.3 + wk * 0.018, 3)
        parts.append(f'<rect class="c" x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{SHADES[lv]}" style="animation-delay:{delay}s"/>')
    return svg(830, 190, "".join(parts))


def activity(days, total, top):
    months = OrderedDict()
    for d in days:
        months.setdefault(d["date"][:7], 0)
        months[d["date"][:7]] += d["count"]
    keys = list(months)[-12:]
    vals = [months[k] for k in keys]
    best = max(vals) if vals else 0
    active = sum(1 for d in days if d["count"] > 0)
    run = longest = 0
    for d in days:
        run = run + 1 if d["count"] > 0 else 0
        longest = max(longest, run)
    busiest = max(days, key=lambda d: d["count"])
    names = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    base, ch, bw, step, x0 = 190, 110, 34, 50, 40
    parts = [
        f'<g class="a"><text x="28" y="40" style="{MONO};font-size:12px;letter-spacing:2px" fill="{BLUE}">LAST 12 MONTHS</text>'
        f'<text x="28" y="76" style="{SERIF};font-size:40px" fill="{INK}">{total} <tspan style="font-size:20px" fill="{MUTE}">contributions</tspan></text></g>',
    ]
    for i, (k, v) in enumerate(zip(keys, vals)):
        h = max(3, round(ch * v / best)) if best else 3
        x = x0 + i * step
        col = BLUE if v == best and best > 0 else INK
        parts.append(f'<rect class="b" x="{x}" y="{base-h}" width="{bw}" height="{h}" rx="4" fill="{col}" style="animation-delay:{0.2+i*0.06:.2f}s"/>')
        if col == BLUE:
            parts.append(f'<text x="{x+bw/2}" y="{base-h-8}" text-anchor="middle" style="{MONO};font-size:12px" fill="{BLUE}">{v}</text>')
        parts.append(f'<text x="{x+bw/2}" y="{base+18}" text-anchor="middle" style="{MONO};font-size:11px" fill="{MUTE}">{names[int(k[5:])-1]}</text>')
    stats = [("active days", str(active)), ("longest streak", f"{longest} days"),
             ("busiest day", f"{busiest['count']}")]
    for i, (lab, val) in enumerate(stats):
        y = 70 + i * 52
        parts.append(f'<g class="a" style="animation-delay:{0.6+i*0.15}s"><text x="690" y="{y}" style="{SERIF};font-size:34px" fill="{INK}">{val}</text>'
                     f'<text x="690" y="{y+18}" style="{MONO};font-size:11px" fill="{MUTE}">{lab}</text></g>')
    return svg(830, 230, "".join(parts))


def main():
    refresh()
    days = sorted(json.loads(DATA.read_text()), key=lambda d: d["date"])
    total = sum(d["count"] for d in days)
    top = max(d["count"] for d in days) or 1
    OUT.mkdir(exist_ok=True)
    (OUT / "heatmap.svg").write_text(heatmap(days, total, top))
    (OUT / "activity.svg").write_text(activity(days, total, top))
    print(f"drew cards for {len(days)} days, {total} contributions")


if __name__ == "__main__":
    main()
