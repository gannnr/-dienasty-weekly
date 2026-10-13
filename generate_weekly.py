#!/usr/bin/env python3
"""Build DieNasty's latest completed weekly recap from the public Sleeper API."""
import html
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

LEAGUE_ID = "1312113845380083712"
BASE = "https://api.sleeper.app/v1"
HEADERS = {"User-Agent": "DieNasty-Weekly/1.0", "Accept": "application/json"}

def api(path):
    request = urllib.request.Request(BASE + path, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)

def safe(value):
    return html.escape(str(value), quote=True)

def fmt(num):
    return f"{float(num or 0):,.2f}"

def build():
    league = api("/league/" + LEAGUE_ID)
    if str(league.get("season")) != "2026":
        raise ValueError("Unexpected league season; refusing to publish")
    users = api("/league/" + LEAGUE_ID + "/users")
    rosters = api("/league/" + LEAGUE_ID + "/rosters")
    state = api("/state/nfl")
    # NFL state advances week after games; current NFL week may still be in progress.
    max_week = min(18, int(state.get("week", 1)))
    names = {u["user_id"]: u.get("metadata", {}).get("team_name") or u.get("display_name") or "Unknown" for u in users}
    teams = {int(r["roster_id"]): names.get(r.get("owner_id"), "Roster " + str(r["roster_id"])) for r in rosters}
    expected = set(teams)
    completed = []
    score_by_week = {}
    for week in range(1, max_week + 1):
        games = api(f"/league/{LEAGUE_ID}/matchups/{week}")
        if not games or set(int(g["roster_id"]) for g in games) != expected:
            continue
        if any(g.get("points") is None or g.get("matchup_id") is None for g in games):
            continue
        paired = defaultdict(list)
        for g in games:
            paired[g["matchup_id"]].append(g)
        if any(len(v) != 2 for v in paired.values()):
            continue
        # Only publish an NFL week after the league has moved beyond it.
        # Exception: allow a completed week after the NFL regular season ends.
        if week >= int(state.get("week", 1)) and state.get("season_type") != "post":
            continue
        if any(float(g.get("points", 0)) == 0 for g in games):
            continue
        completed.append(week)
        score_by_week[week] = games
    if not completed:
        raise ValueError("No safely completed week found; preserving existing site")
    latest = max(completed)
    totals = defaultdict(float)
    wins = defaultdict(int)
    losses = defaultdict(int)
    weekly_wins = {}
    for week in sorted(score_by_week):
        games = score_by_week[week]
        paired = defaultdict(list)
        for g in games:
            rid = int(g["roster_id"])
            totals[rid] += float(g["points"])
            paired[g["matchup_id"]].append(g)
        if week == latest:
            weekly_wins = {}
        for pair in paired.values():
            a,b = pair
            ra,rb = int(a["roster_id"]),int(b["roster_id"])
            pa,pb = float(a["points"]),float(b["points"])
            if pa > pb: wins[ra] += 1; losses[rb] += 1
            elif pb > pa: wins[rb] += 1; losses[ra] += 1
            if week == latest:
                weekly_wins[ra] = (rb,pa,pb)
                weekly_wins[rb] = (ra,pb,pa)
    current = {int(g["roster_id"]):float(g["points"]) for g in score_by_week[latest]}
    rank = sorted(expected,key=lambda r:(-current[r],-totals[r]))
    allplay = {rid:sum(current[rid]>current[other] for other in expected if other!=rid) for rid in expected}
    most = rank[0]
    least = rank[-1]
    style = """<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0b1020;color:#f7f9fc;font:15px/1.55 system-ui,-apple-system,sans-serif}
main{max-width:820px;margin:auto;padding:32px 16px 80px}h1{font-size:clamp(38px,8vw,64px);line-height:1.02;letter-spacing:-.05em;margin:8px 0 16px}
h2{font-size:25px;margin:32px 0 12px}.small{color:#a9b4c8;font-size:12px}.intro{color:#c8d2e2}.eyebrow{letter-spacing:.14em;color:#b49cff;font-weight:900;font-size:12px}
.card{background:#172039;border:1px solid #32405b;border-radius:18px;padding:18px;margin:10px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
strong{color:#fff}.accent{color:#52df86}.bad{color:#ff6881}summary{cursor:pointer;display:flex;justify-content:space-between;gap:8px;align-items:center;font-weight:750}
details>p{color:#d1daea;margin-bottom:0}.table{width:100%;border-collapse:collapse;font-size:13px}.table th{text-align:left;color:#a9b4c8}.table th,.table td{padding:10px 6px;border-bottom:1px solid #35415b}.table td:last-child,.table th:last-child{text-align:right}
a{color:#91c7ff}footer{margin-top:32px;color:#a9b4c8;font-size:12px}
</style>"""
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DieNasty — Week '+str(latest)+'</title>',style,'</head><body><main>']
    parts += ['<div class="eyebrow">DIENASTY 4 LYFE · AUTOMATED WEEKLY RECAP</div>',
              f'<h1>WEEK {latest}<br>JUST DROPPED.</h1>',
              '<p class="intro">Actual Sleeper matchup scores. Fresh receipts, real records, and mathematically verified weekly rankings.</p>',
              '<div class="cards"><div class="card"><span class="small">WEEKLY FINAL BOSS</span><h2>'+safe(teams[most])+'</h2><strong class="accent">'+fmt(current[most])+' pts</strong><p>Top score. The rest of the league is filing complaints.</p></div>',
              '<div class="card"><span class="small">WEEKLY BASEMENT</span><h2>'+safe(teams[least])+'</h2><strong class="bad">'+fmt(current[least])+' pts</strong><p>Congratulations on your extremely exclusive appointment with the floor.</p></div></div>',
              '<h2>Manager receipts</h2>']
    for rid in sorted(expected,key=lambda r:(-wins[r],-totals[r])):
        matchup = weekly_wins.get(rid)
        if matchup is None: continue
        opponent,own,opp = matchup
        result = "W" if own>opp else ("L" if own<opp else "T")
        remark = ("Cooked the competition." if result=="W" else "The scoreboard did not cooperate." if result=="L" else "A rare diplomatic stalemate.")
        record = f'{wins[rid]}-{losses[rid]}'
        parts += [f'<details class="card"><summary><span>{safe(teams[rid])} <span class="small">({record})</span></span><span class="{ "accent" if result=="W" else "bad" }">{result} · {fmt(own)}</span></summary>',
                  f'<p><strong>Week {latest}:</strong> {safe(teams[rid])} vs. {safe(teams[opponent])}, {fmt(own)}–{fmt(opp)}. {remark}</p>',
                  f'<p><strong>All-play:</strong> {allplay[rid]}-{len(expected)-1-allplay[rid]} this week. <strong>Season points:</strong> {fmt(totals[rid])}.</p></details>']
    parts += ['<h2>Weekly scoreboard</h2><div class="card"><table class="table"><thead><tr><th>Rank</th><th>Manager</th><th>Record</th><th>Points</th></tr></thead><tbody>']
    for i,rid in enumerate(rank,1):
        parts += [f'<tr><td>{i}</td><td>{safe(teams[rid])}</td><td>{wins[rid]}-{losses[rid]}</td><td>{fmt(current[rid])}</td></tr>']
    parts += ['</tbody></table></div>',
              '<h2>Weekly hardware</h2><div class="cards">',
              f'<div class="card"><strong>💣 Offensive War Crime</strong><p>{safe(teams[most])}: {fmt(current[most])} points. No further questions.</p></div>',
              f'<div class="card"><strong>💀 Basement Certified</strong><p>{safe(teams[least])}: {fmt(current[least])} points. Cursed.</p></div>']
    unlucky = sorted(expected,key=lambda r:(-current[r],r))
    unlucky = next((rid for rid in unlucky if weekly_wins[rid][1] < weekly_wins[rid][2]),None)
    if unlucky is not None:
        parts.append(f'<div class="card"><strong>🧂 Schedule Victim</strong><p>{safe(teams[unlucky])}: {fmt(current[unlucky])} points in a loss. The matchup gods are doing bits.</p></div>')
    now = datetime.now(ZoneInfo("America/Chicago")).strftime("%B %d, %Y at %I:%M %p CT")
    parts += ['</div><footer>Generated '+safe(now)+' · Sleeper league '+LEAGUE_ID+' · Week '+str(latest)+' validated as completed.<br>Advanced NFL opportunity metrics are intentionally excluded until verified for this week.</footer></main></body></html>']
    destination = "index.html"
    content = "".join(parts)
    if not os.environ.get("FORCE_WRITE") and os.path.isfile(destination):
        previous = open(destination,encoding="utf-8").read()
        import re
        found = re.search(r'<h1>WEEK\s+(\d+)',previous)
        if found and int(found.group(1)) > latest:
            raise ValueError("Existing report newer than generated week")
    with open(destination,"w",encoding="utf-8") as handle: handle.write(content)
    print(f"Successfully generated DieNasty Week {latest}, {len(expected)} managers")

if __name__=="__main__":
    try: build()
    except Exception as error:
        print("SAFE FAILURE (existing page unchanged):",error,file=sys.stderr)
        sys.exit(1)
