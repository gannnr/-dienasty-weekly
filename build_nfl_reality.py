#!/usr/bin/env python3
"""Build a week-matched NFL Reality Check from nflverse's public player-game data."""
import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

URL="https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv"
def num(v):
    try: return float(v or 0)
    except (ValueError, TypeError): return 0.0
def n(v): return int(round(num(v)))
def build(week,season=2026):
    path=Path("data")/f"nfl_week_{season}_{week}.json"
    if path.exists():
        old=json.loads(path.read_text())
        if old.get("week")==week and old.get("season")==season and len(old.get("players",[]))==3:
            print("Verified NFL snapshot already present:",path)
            return
    request=urllib.request.Request(URL,headers={"User-Agent":"DieNasty-Weekly/1.0"})
    with urllib.request.urlopen(request,timeout=85) as response:
        reader=csv.DictReader(io.TextIOWrapper(response,encoding="utf-8-sig"))
        rows=[r for r in reader if r.get("season")==str(season) and r.get("week")==str(week) and r.get("season_type","REG")=="REG"]
    if len(rows)<100:
        raise ValueError(f"Insufficient verified NFL player-game records for {season} week {week}: {len(rows)}")
    by_position={}
    for r in rows:
        pos=r.get("position","")
        if pos=="QB":
            score=num(r.get("passing_yards"))/25+4*num(r.get("passing_tds"))+num(r.get("rushing_yards"))/10+6*num(r.get("rushing_tds"))
        elif pos=="RB":
            score=num(r.get("rushing_yards"))/10+6*num(r.get("rushing_tds"))+num(r.get("receptions"))+num(r.get("receiving_yards"))/10+6*num(r.get("receiving_tds"))
        elif pos in ("WR","TE"):
            score=num(r.get("receptions"))+num(r.get("receiving_yards"))/10+6*num(r.get("receiving_tds"))
        else: continue
        if not r.get("player_display_name") or not r.get("recent_team"): continue
        if pos not in by_position or score>by_position[pos][0]:
            by_position[pos]=(score,r)
    if not all(x in by_position for x in ("QB","RB")) or not ("WR" in by_position or "TE" in by_position):
        raise ValueError("Missing position coverage in NFL stats")
    receiver=max((by_position[k] for k in ("WR","TE") if k in by_position),key=lambda a:a[0])[1]
    rb=by_position["RB"][1];qb=by_position["QB"][1]
    def base(r,kind,label,metrics,story):
        return {"name":r["player_display_name"],"team":r["recent_team"],
                "opponent":r.get("opponent_team",""),"kind":kind,"label":label,
                "metrics":metrics,"story":story}
    result=[
        base(receiver,"receiving","TARGET VACUUM",
          [["TARGETS",n(receiver.get("targets"))],["RECEPTIONS",n(receiver.get("receptions"))],["REC YARDS",n(receiver.get("receiving_yards"))],["REC TD",n(receiver.get("receiving_tds"))]],
          f"{n(receiver.get('targets'))} targets, {n(receiver.get('receptions'))} catches and {n(receiver.get('receiving_yards'))} receiving yards. Certified receiving-volume takeover."),
        base(rb,"rushing","WORKLOAD LANDLORD",
          [["CARRIES",n(rb.get("carries"))],["TARGETS",n(rb.get("targets"))],["RUSH YARDS",n(rb.get("rushing_yards"))],["RUSH TD",n(rb.get("rushing_tds"))]],
          f"{n(rb.get('carries'))} carries, {n(rb.get('targets'))} targets and {n(rb.get('rushing_tds'))} rushing touchdowns. The workload department has one employee."),
        base(qb,"passing","AIR RAID COMMANDER",
          [["ATTEMPTS",n(qb.get("attempts"))],["COMPLETIONS",n(qb.get("completions"))],["PASS YARDS",n(qb.get("passing_yards"))],["PASS TD",n(qb.get("passing_tds"))]],
          f"{n(qb.get('passing_yards'))} passing yards and {n(qb.get('passing_tds'))} passing touchdowns on {n(qb.get('attempts'))} attempts. The box score has entered its villain era.")
    ]
    path.parent.mkdir(exist_ok=True,parents=True)
    path.write_text(json.dumps({"season":season,"week":week,"source":"nflverse public player_stats weekly game data","players":result},indent=2)+"\n")
    print("Created verified NFL Reality Check:",path)
if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit("Usage: python build_nfl_reality.py WEEK")
    build(int(sys.argv[1]))
