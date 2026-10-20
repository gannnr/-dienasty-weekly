#!/usr/bin/env python3
"""Build DieNasty's latest completed weekly recap from the public Sleeper API."""
import html
import json
from pathlib import Path
from weekly_awardz import assign as assign_awardz, render as render_awardz
from ai_narratives import generate as generate_ai_narratives
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
    league_avatar = league.get('avatar')
    users = api("/league/" + LEAGUE_ID + "/users")
    rosters = api("/league/" + LEAGUE_ID + "/rosters")
    state = api("/state/nfl")
    # NFL state advances week after games; current NFL week may still be in progress.
    max_week = min(18, int(state.get("week", 1)))
    names = {u["user_id"]: u.get("metadata", {}).get("team_name") or u.get("display_name") or "Unknown" for u in users}
    teams = {int(r["roster_id"]): names.get(r.get("owner_id"), "Roster " + str(r["roster_id"])) for r in rosters}
    expected = set(teams)
    avatar_file = Path('data/manager_avatars.json')
    avatars = json.loads(avatar_file.read_text()) if avatar_file.exists() else {}
    def photo(rid):
        url = avatars.get(str(next((r.get('owner_id') for r in rosters if int(r['roster_id'])==rid),'')))
        return '<img class="manager-avatar" src="'+safe(url)+'" alt="Manager avatar">' if url else ''
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
    expected_wins = defaultdict(float)
    wins = defaultdict(int)
    losses = defaultdict(int)
    weekly_wins = {}
    for week in sorted(score_by_week):
        games = score_by_week[week]
        paired = defaultdict(list)
        week_scores = {int(g["roster_id"]):float(g["points"]) for g in games}
        for rid,score in week_scores.items():
            expected_wins[rid] += sum(score > other for other_rid,other in week_scores.items() if other_rid != rid)/(len(week_scores)-1)
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
    names_by_player = {}
    try:
        raw_players = api("/players/nfl")
        names_by_player = {pid: p.get("full_name") or (p.get("first_name","") + " " + p.get("last_name","")).strip() for pid,p in raw_players.items()}
    except Exception as error:
        print("Player-name lookup unavailable:", error)
    def best_ball_text(rid):
        game = next(g for g in score_by_week[latest] if int(g["roster_id"]) == rid)
        points = game.get("players_points") or {}
        active = game.get("starters") or []
        leaders = sorted(((float(points.get(pid) or 0), pid) for pid in active if pid and pid != "0"),reverse=True)[:3]
        return ", ".join(f"{safe(names_by_player.get(pid) or pid)} {fmt(score)}" for score,pid in leaders) or "Not available"

    rank = sorted(expected,key=lambda r:(-current[r],-totals[r]))
    allplay = {rid:sum(current[rid]>current[other] for other in expected if other!=rid) for rid in expected}
    most = rank[0]
    least = rank[-1]
    ordered = sorted(expected, key=lambda r: (-wins[r], -totals[r]))
    season_rank = sorted(expected, key=lambda r: -totals[r])
    lucky_team = max(expected,key=lambda r: wins[r]-expected_wins[r])
    cursed_team = min(expected,key=lambda r: wins[r]-expected_wins[r])
    max_score = max(current.values())
    if len(expected) != 10 or len(score_by_week[latest]) != 10:
        raise ValueError('Expected ten DieNasty teams; retaining published report')
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
footer{color:var(--muted);font-size:12px;margin-top:36px}\n.manager-avatar{width:42px;height:42px;object-fit:cover;border-radius:50%;vertical-align:middle;border:2px solid #69b1ff;margin-right:8px;flex-shrink:0}.manager{font-size:12px;line-height:1.1;min-width:0;flex:1;overflow-wrap:anywhere;display:flex;align-items:center}.record{min-width:58px}.pill{flex-shrink:0;font-size:10px}.award-heading{display:flex;align-items:center;gap:12px;margin-bottom:12px}.award-icon{width:56px;height:56px;object-fit:contain;flex-shrink:0}.award-heading .label{font-size:11px}.award-recipient{display:flex;align-items:center;gap:7px;overflow-wrap:anywhere}.nfl-player-header{display:flex;align-items:center;gap:13px;margin:12px 0}.nfl-headshot{width:76px;height:76px;object-fit:contain;background:#28354e;border-radius:16px;border:2px solid #69b1ff}
@media(max-width:500px){.league-logo{width:72px;height:72px}}.hero-title{display:flex;align-items:center;gap:16px}.hero-title h1{min-width:0}.league-logo{width:92px;height:92px;object-fit:cover;border-radius:20px;flex-shrink:0;border:2px solid #b49cff;background:#19213a}</style>"""
    def esc(r):
        return safe(teams[r].strip())
    def card(title, body, tag="LEAGUE RECEIPTS"):
        return f'<div class="card"><span class="label">{safe(tag)}</span><h3>{safe(title)}</h3><p>{body}</p></div>'
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DieNasty — Week '+str(latest)+'</title>',style,'</head><body><main>']
    now = datetime.now(ZoneInfo("America/Chicago")).strftime("%B %d, %Y at %I:%M %p CT")
    logo = ('<img class="league-logo" src="assets/league-logo.png" alt="DieNasty league logo">') if league_avatar else ''
    parts += [f'<div class="eyebrow">DIENASTY 4 LYFE · THE WEEKLY DAMAGE REPORT</div><div class="hero-title">{logo}<h1>WEEK {latest}<br>IS UNWELL.</h1></div>',
              f'<p class="intro">Best ball. League receipts, matchup chaos, and actual math to back up the slander.</p><p class="small">Updated {safe(now)} · Verified Sleeper results</p>']
    parts += ['<section>',card(f'{teams[most].strip()} chose violence',f'{photo(most)} <span class="big">{fmt(current[most])} points.</span> Weekly high score, {allplay[most]}-{len(expected)-1-allplay[most]} in all-play, and a fresh invoice for everyone below them.','MAIN CHARACTER'),'</section>']
    weekly_history = {wk:{int(g["roster_id"]):float(g["points"]) for g in games} for wk,games in score_by_week.items()}
    lineups = {int(g["roster_id"]):[(pid,float((g.get("players_points") or {}).get(pid) or 0)) for pid in (g.get("starters") or []) if pid and pid != "0"] for g in score_by_week[latest]}
    positions = {pid:entry.get("position") for pid,entry in (raw_players.items() if "raw_players" in locals() else [])}
    awardz = assign_awardz(latest,teams,current,weekly_wins,wins,expected_wins,totals,weekly_history,lineups,names_by_player,positions)
    parts.append(render_awardz(awardz, {int(r['roster_id']):avatars.get(str(r.get('owner_id'))) for r in rosters}))
    parts += ['<h2>State of every bro</h2><p class="small">Tap your team. Scoreboard first, full receipts underneath.</p>']
    facts=[]
    for fid in ordered:
        foe, own_score, foe_score = weekly_wins[fid]
        facts.append({
            "roster_id":fid,"manager":teams[fid],"season":2026,"week":latest,
            "result":"WIN" if own_score>foe_score else "LOSS" if own_score<foe_score else "TIE",
            "opponent":teams[foe] if isinstance(foe,int) and foe in teams else str(foe),
            "weekly_points":fmt(own_score),"opponent_points":fmt(foe_score),
            "weekly_rank":rank.index(fid)+1,"weekly_allplay_wins":allplay[fid],
            "weekly_allplay_losses":len(expected)-1-allplay[fid],
            "season_record":f"{wins[fid]}-{losses[fid]}",
            "season_total_points":fmt(totals[fid]),
            "season_points_rank":season_rank.index(fid)+1,
            "scoring_deserved_wins":f"{expected_wins[fid]:.2f}",
            "actual_wins":wins[fid],"top_best_ball_contributors":best_ball_text(fid)
        })
    ai_narratives=generate_ai_narratives(latest,facts)
    ai_by_id={item["roster_id"]:item for item in ai_narratives["managers"]} if ai_narratives else {}
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
        leaders = best_ball_text(rid)
        if leaders != 'Not available':
            match_story += ' Top lineup contributors: ' + leaders + '.'
        if rid in ai_by_id:
            narrative=ai_by_id[rid]
            story_html=(
                '<h3 class="story-headline">'+safe(narrative["headline"])+'</h3>'
                +'<p><strong>THE FILM ROOM</strong> '+safe(narrative["film_room"])+'</p>'
                +'<p><strong>THE BIGGER CONSPIRACY</strong> '+safe(narrative["bigger_conspiracy"])+'</p>'
                +'<p><strong>NEXT EPISODE</strong> '+safe(narrative["next_episode"])+'</p>'
            )
        else:
            story_html=(f'<p><strong>Match:</strong> {esc(rid)} {"beat" if result=="WIN" else "lost to" if result=="LOSS" else "tied"} {esc(opponent)}, {fmt(own)}–{fmt(opp)}. {match_story}</p>'
                +f'<p><strong>Season vibe:</strong> #{season_place} in total points with a {record} record. {season_story} Scoring-deserved wins: {expected_wins[rid]:.2f}; actual: {wins[rid]}.</p>')
        parts += [f'<details class="card"><summary><span class="record">{record}</span><span class="manager">{photo(rid)} {esc(rid)}</span><span class="pill {"good" if result=="WIN" else "bad"}">{result} · {fmt(own)}</span></summary>',
            f'<div class="facts"><div class="fact"><span>WEEK {latest} POINTS</span><b>{fmt(own)}</b></div><div class="fact"><span>WEEKLY RANK</span><b>#{placement} / {n}</b></div><div class="fact"><span>ALL-PLAY THIS WEEK</span><b>{ap}-{n-1-ap}</b></div><div class="fact"><span>SEASON POINTS</span><b>{fmt(totals[rid])}</b></div></div>',
            story_html,
            f'<p><strong>Top automatic best-ball scorers:</strong> {best_ball_text(rid)}</p></details>']
    # Week-by-week all-play record, directly after the manager cards.
    parts += [f'<h2>Week {latest} All-Play Record</h2><p class="small">How many of the other nine teams each manager outscored this week. This is NOT the head-to-head record.</p><div class="card"><table><thead><tr><th>Rank</th><th>Manager</th><th>All-play</th><th>Week pts</th></tr></thead><tbody>']
    for i,rid in enumerate(rank,1):
        parts.append(f'<tr><td>{i}</td><td>{esc(rid)}</td><td>{allplay[rid]}-{len(expected)-1-allplay[rid]}</td><td>{fmt(current[rid])}</td></tr>')
    parts += ['</tbody></table></div>']

    # Rank chart dots and rows by actual minus expected season wins.
    luck_order = sorted(expected,key=lambda r:(-(wins[r]-expected_wins[r]),-wins[r],r))
    parts += ['<h2>Total Season Lucky Dawg Rankings</h2><p class="small">Actual minus expected wins. Positive = favorable matchups; negative = brutal scheduling. Every week, 9-0 all-play earns 1 expected win, not 9 actual wins.</p>']
    upper=max(1,latest)
    def sx(value):return 55+485*value/upper
    def sy(value):return 452-395*value/upper
    parts += ['<div class="card"><svg viewBox="0 0 600 515" role="img" aria-label="Season lucky dawg rankings: expected versus actual wins" style="width:100%;height:auto">']
    for tick in range(upper+1):
        xx,yy=sx(tick),sy(tick)
        parts.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="57" y2="452" stroke="#35415b"/><line x1="55" x2="540" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#35415b"/><text x="{xx:.1f}" y="477" fill="#a9b4c8" font-size="12" text-anchor="middle">{tick}</text><text x="41" y="{yy+4:.1f}" fill="#a9b4c8" font-size="12" text-anchor="end">{tick}</text>')
    parts.append('<line x1="55" y1="452" x2="540" y2="57" stroke="#d1d6df" stroke-width="2" stroke-dasharray="5 5"/><text x="300" y="505" fill="#a9b4c8" font-size="12" text-anchor="middle">EXPECTED WINS</text><text x="16" y="255" fill="#a9b4c8" font-size="12" text-anchor="middle" transform="rotate(-90 16 255)">ACTUAL WINS</text>')
    for i,rid in enumerate(luck_order,1):
        color='#ffc85c' if i==1 else '#b49cff' if i==len(luck_order) else '#69b1ff'
        x,y=sx(expected_wins[rid]),sy(wins[rid])
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="12" fill="{color}" stroke="#0b1020" stroke-width="2"><title>#{i} {esc(rid)}</title></circle><text x="{x:.1f}" y="{y+4:.1f}" fill="#0b1020" text-anchor="middle" font-weight="900" font-size="11">{i}</text>')
    parts += ['</svg><p class="small">Gold = luckiest · Purple = unluckiest · Blue = everyone else. Dot numbers match the table below.</p></div>',
              '<div class="card" style="overflow-x:auto"><table><thead><tr><th>Rank</th><th>Manager</th><th>Expected wins</th><th>Actual wins</th><th>Luck</th></tr></thead><tbody>']
    for i,rid in enumerate(luck_order,1):
        bg='background:rgba(255,200,92,.14);' if i==1 else 'background:rgba(180,156,255,.17);' if i==len(luck_order) else ''
        parts.append(f'<tr style="{bg}"><td>#{i}</td><td>{esc(rid)}</td><td>{expected_wins[rid]:.2f}</td><td>{wins[rid]}</td><td>{wins[rid]-expected_wins[rid]:+.2f}</td></tr>')
    parts += ['</tbody></table></div>']
    # A snapshot must explicitly match the completed report week; never show stale NFL stats.
    snapshot_path = Path('data') / f'nfl_week_2026_{latest}.json'
    if snapshot_path.is_file():
        snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
        if snapshot.get('season') != 2026 or snapshot.get('week') != latest:
            raise ValueError('NFL snapshot season/week mismatch')
        entries = snapshot.get('players') or []
        if len(entries) != 3: raise ValueError('NFL reality check requires exactly three verified player entries')
        parts += ['<h2>NFL reality check</h2><p class="small">Exactly three player eruptions. Real NFL opportunities, not estimated workloads.</p>']
        for entry in entries:
            metrics=entry.get('metrics') or []
            if len(metrics) != 4 or not entry.get('name') or not entry.get('story'):
                raise ValueError('NFL reality-check snapshot is missing required metrics')
            metrics_html=''.join(f'<div class="fact"><span>{safe(label)}</span><b>{safe(value)}</b></div>' for label,value in metrics)
            player_id = entry.get("espn_id")
            headshot = f'https://a.espncdn.com/i/headshots/nfl/players/full/{safe(player_id)}.png' if player_id and str(player_id).isdigit() else 'assets/nfl-headshots/default.svg'
            parts.append(f'<div class="card"><span class="label">{safe(entry.get("label","NFL REALITY"))}</span><div class="nfl-player-header"><img class="nfl-headshot" src="{headshot}" alt="{safe(entry["name"])} headshot" onerror="this.onerror=null;this.src=\'assets/nfl-headshots/default.svg\'"><div><h3>{safe(entry["name"])}</h3><p class="small">{safe(entry.get("team",""))} vs {safe(entry.get("opponent",""))}</p></div></div><div class="facts">{metrics_html}</div><p>{safe(entry["story"])}</p></div>')
    else:
        parts += ['<h2>NFL reality check</h2><div class="card"><p>Advanced NFL player-game stats are awaiting verification for this week. We do not recycle last week\'s numbers.</p></div>']
    parts += ['<h2>Next week\'s propaganda</h2>',
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
    if latest == 5:
        Path("week-5.html").write_text(content,encoding="utf-8")
    archive = Path('data')/'awardz'/f'2026_{latest}.json'
    archive.parent.mkdir(parents=True,exist_ok=True)
    archive.write_text(json.dumps({'season':2026,'week':latest,'awards':awardz},indent=2)+'\n',encoding='utf-8')
    print(f"Successfully generated DieNasty Week {latest}, {len(expected)} managers")

if __name__=="__main__":
    try: build()
    except Exception as error:
        print("SAFE FAILURE (existing page unchanged):",error,file=sys.stderr)
        sys.exit(1)

# Rebuild trigger: publish refreshed Awardz badges, compact manager cards and NFL headshots.

# Trigger supervised Week 5 AI integration test; safe fallback remains enabled.

# Diagnostic run for API request validation.

# JSON format correction integration run.

# Retest AI JSON response validation.

# Funded API verification retry.

# Diagnose AI story word-count gate.

# Weekly schedule repair verification, October 2026.

# Verified Week 6 AI retry test.

# Rebuild Week 6 with verified NFL Reality Check snapshot.
