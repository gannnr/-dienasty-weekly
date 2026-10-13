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
    ordered = sorted(expected, key=lambda r: (-wins[r], -totals[r]))
    season_rank = sorted(expected, key=lambda r: -totals[r])
    max_score = max(current.values())
    max_season = max(totals.values())
    games = [(rid, *weekly_wins[rid]) for rid in expected if rid < weekly_wins[rid][0]]
    close = min(games, key=lambda g: abs(g[2] - g[3]))
    biggest = max(games, key=lambda g: abs(g[2] - g[3]))
    unlucky = next((r for r in rank if weekly_wins[r][1] < weekly_wins[r][2]), None)
    lucky = next((r for r in reversed(rank) if weekly_wins[r][1] > weekly_wins[r][2]), None)
    style = """<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#172039;--muted:#a9b4c8;--line:#35415b;--green:#52df86;--red:#ff6881;--gold:#ffc85c;--purple:#b49cff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#f7f9fc;font:15px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:780px;margin:auto;padding:25px 16px 72px}h1{font-size:clamp(44px,10vw,65px);letter-spacing:-.05em;line-height:1.05;margin:10px 0 16px}h2{font-size:26px;letter-spacing:-.035em;margin:34px 0 7px}
h3{margin:6px 0 7px;font-size:19px}.eyebrow{font-size:12px;font-weight:900;letter-spacing:.13em;color:#b8c4d7}
.intro{font-size:16px;color:#c8d2e2;margin:0 0 22px}.small{font-size:12px;color:var(--muted)}
.card{background:linear-gradient(180deg,#172039,#121a30);border:1px solid var(--line);border-radius:20px;padding:17px;margin:10px 0}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:10px}.two .card{margin:0}
.label{display:inline-block;background:#3a2942;color:#ffb8c5;font-size:10px;font-weight:900;letter-spacing:.07em;border-radius:99px;padding:5px 9px}
p{color:#cbd4e4;margin:8px 0;line-height:1.5}.big{font-size:27px;font-weight:950}.good{color:var(--green)}.bad{color:var(--red)}
details summary{cursor:pointer;list-style:none;display:flex;align-items:center;justify-content:space-between;gap:10px}summary::-webkit-details-marker{display:none}
.record{font-size:25px;font-weight:950;min-width:56px}.manager{font-size:14px;font-weight:900}.pill{font-size:11px;font-weight:850;white-space:nowrap}
.facts{display:grid;grid-template-columns:repeat(2,1fr);gap:7px;margin:13px 0}.fact{background:#242d43;border-radius:10px;padding:10px}.fact b{font-size:17px;display:block}.fact span{display:block;font-size:10px;color:var(--muted)}
.track{height:11px;background:#303a50;border-radius:10px;overflow:hidden;flex:1}.bar{display:block;height:100%;background:linear-gradient(90deg,#69b1ff,#32d3c4);border-radius:10px}
.line{display:flex;align-items:center;gap:8px;margin:10px 0}.line .name{width:145px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:800}.line .value{width:74px;text-align:right;font-size:11px}
table{border-collapse:collapse;width:100%;font-size:12px}th{text-align:left;color:var(--muted)}td,th{border-bottom:1px solid var(--line);padding:10px 5px}td:last-child,th:last-child{text-align:right}
footer{color:var(--muted);font-size:12px;margin-top:36px}
</style>"""
    def esc(r):
        return safe(teams[r].strip())
    def card(title, body, tag="LEAGUE RECEIPTS"):
        return f'<div class="card"><span class="label">{safe(tag)}</span><h3>{safe(title)}</h3><p>{body}</p></div>'
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DieNasty — Week '+str(latest)+'</title>',style,'</head><body><main>']
    now = datetime.now(ZoneInfo("America/Chicago")).strftime("%B %d, %Y at %I:%M %p CT")
    parts += [f'<div class="eyebrow">DIENASTY 4 LYFE · CURRENT WEEK</div><h1>WEEK {latest}<br>JUST DROPPED.</h1>',
              f'<p class="intro">Best ball. League receipts, matchup chaos, and actual math to back up the slander.</p><p class="small">Updated {safe(now)} · Verified Sleeper results</p>']
    parts += ['<section>',card(f'{teams[most].strip()} chose violence',f'<span class="big">{fmt(current[most])} points.</span> Weekly high score, {allplay[most]}-{len(expected)-1-allplay[most]} in all-play, and a fresh invoice for everyone below them.','MAIN CHARACTER'),'</section>']
    parts += ['<h2>League-wide brainrot</h2><p class="small">The storylines before you scroll to your own team.</p><div class="two">']
    parts += [card("The scoreboard has a new landlord",f'{esc(most)} dropped {fmt(current[most])} and finished first of {len(expected)} teams this week.','WEEKLY FINAL BOSS')]
    parts += [card("Maximum schedule pain",f'{esc(unlucky)} scored {fmt(current[unlucky])} but still lost {fmt(weekly_wins[unlucky][1])}–{fmt(weekly_wins[unlucky][2])}. The algorithm is doing stand-up comedy.','CURSED') if unlucky is not None else card("No schedule victims", "Nobody posted a loss from the top end of the scoreboard this time.","WEEKLY CHAOS")]
    parts += [card("The photo finish",f'{esc(close[0])} and {esc(close[1])} finished {fmt(close[2])}–{fmt(close[3])}. Margin: {fmt(abs(close[2]-close[3]))} points. The group chat should investigate.','CLOSEST MATCH')]
    parts += [card("The week was not equally distributed",f'{esc(biggest[0])} versus {esc(biggest[1])}: {fmt(biggest[2])}–{fmt(biggest[3])}. That is a {fmt(abs(biggest[2]-biggest[3]))}-point difference.','BIGGEST BLOWOUT')]
    parts += ['</div><h2>State of every bro</h2><p class="small">Tap your team. Scoreboard first, full receipts underneath.</p>']
    for rid in ordered:
        opponent, own, opp = weekly_wins[rid]
        result = "WIN" if own>opp else ("LOSS" if own<opp else "TIE")
        placement = rank.index(rid)+1
        season_place = season_rank.index(rid)+1
        n=len(expected)
        ap=allplay[rid]
        if result=="WIN" and placement>n//2:
            match_story="Got the W from the bottom half of weekly scoring. Timing is an elite fantasy skill."
        elif result=="LOSS" and placement<=n//2:
            match_story="Lost despite finishing in the top half of weekly scoring. Certified schedule violence."
        elif result=="WIN":
            match_story="Scored enough to win and actually got rewarded for it. Rare administrative competence."
        else:
            match_story="Opponent had more points. The scoreboard is a ruthless unpaid intern."
        if ap>=n-2:
            season_story="The weekly output was elite. Opponents should start reviewing their insurance."
        elif ap<=1:
            season_story="A brutal weekly all-play showing. Redemption arc pending approval."
        else:
            season_story=f'This was a #{placement} weekly score, while your season-long points rank is #{season_place}.'
        record=f'{wins[rid]}-{losses[rid]}'
        parts += [f'<details class="card"><summary><span class="record">{record}</span><span class="manager">{esc(rid)}</span><span class="pill {"good" if result=="WIN" else "bad"}">{result} · {fmt(own)}</span></summary>',
            f'<div class="facts"><div class="fact"><span>WEEK {latest} POINTS</span><b>{fmt(own)}</b></div><div class="fact"><span>WEEKLY RANK</span><b>#{placement} / {n}</b></div><div class="fact"><span>ALL-PLAY THIS WEEK</span><b>{ap}-{n-1-ap}</b></div><div class="fact"><span>SEASON POINTS</span><b>{fmt(totals[rid])}</b></div></div>',
            f'<p><strong>Match:</strong> {esc(rid)} {"beat" if result=="WIN" else "lost to" if result=="LOSS" else "tied"} {esc(opponent)}, {fmt(own)}–{fmt(opp)}. {match_story}</p>',
            f'<p><strong>Season vibe:</strong> #{season_place} in total points with a {record} record. {season_story}</p></details>']
    parts += ['<h2>Weekly scoring ladder</h2><p class="small">Actual Sleeper fantasy points, descending.</p><div class="card">']
    for rid in rank:
        parts += [f'<div class="line"><span class="name">{esc(rid)}</span><span class="track"><span class="bar" style="width:{100*current[rid]/max_score:.1f}%"></span></span><span class="value">{fmt(current[rid])}</span></div>']
    parts += ['</div><h2>Season points vs. record</h2><p class="small">Who is thriving and who keeps getting robbed?</p><div class="card">']
    for rid in season_rank:
        parts += [f'<div class="line"><span class="name">{esc(rid)}</span><span class="track"><span class="bar" style="width:{100*totals[rid]/max_season:.1f}%"></span></span><span class="value">{wins[rid]}-{losses[rid]}</span></div>']
    parts += ['</div><h2>Schedule justice</h2><p class="small">Weekly all-play records, independent of assigned opponents.</p><div class="card"><table><thead><tr><th>Manager</th><th>Week rank</th><th>All-play</th><th>Outcome</th></tr></thead><tbody>']
    for rid in rank:
        parts += [f'<tr><td>{esc(rid)}</td><td>#{rank.index(rid)+1}</td><td>{allplay[rid]}-{len(expected)-1-allplay[rid]}</td><td>{"W" if weekly_wins[rid][1]>weekly_wins[rid][2] else "L"}</td></tr>']
    parts += ['</tbody></table></div><h2>Weekly hardware</h2><div class="two">',
        card("Offensive war crime", f'{esc(most)} posted {fmt(current[most])} and won the scoring crown.','💣 HIGH SCORE'),
        card("Basement certified", f'{esc(least)} recorded {fmt(current[least])}. This week is going in the evidence locker.','💀 CURSED'),
        card("Margin of terror", f'{esc(biggest[0])} vs. {esc(biggest[1])} was decided by {fmt(abs(biggest[2]-biggest[3]))} points.','🚨 BLOWOUT')]
    if unlucky is not None:
        parts += [card("Schedule pain",f'{esc(unlucky)} put up {fmt(current[unlucky])} and still caught an L.','🧂 ROBBED')]
    if lucky is not None:
        parts += [card("Schedule privilege",f'{esc(lucky)} won with {fmt(current[lucky])} despite being #{rank.index(lucky)+1} in scoring.','🎰 LUCKY')]
    parts += ['</div><h2>Next week\'s propaganda</h2>',
        card("The receipts do not expire",f'{esc(most)} has the weekly crown, {esc(least)} needs a bounce-back, and the remaining managers have seven days to manufacture excuses.','LOOKING AHEAD'),
        f'<footer>Updated {safe(now)} · Sleeper league {LEAGUE_ID} · Completed Week {latest}. Scores, standings and all-play computed from actual Sleeper matchups. NFL player opportunity data is omitted unless independently verified — no fake carries, targets or projections.</footer></main></body></html>']
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

# Rebuild trigger: publish upgraded weekly page immediately.
