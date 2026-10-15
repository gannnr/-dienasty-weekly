#!/usr/bin/env python3
"""Refresh the three NFL Reality Check cards from private Supabase data.

Optional, never publicly embeds credentials. If credentials aren't configured,
the existing verified weekly snapshot is used (only for the matching week).
"""
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SEASON = 2026

def get(path, params):
    url = BASE + "/rest/v1/" + path + "?" + urlencode(params)
    req = Request(url, headers={"apikey":KEY,"Authorization":"Bearer "+KEY,"Accept":"application/json"})
    with urlopen(req, timeout=35) as r:
        return json.load(r)

def number(value):
    return float(value or 0)

def read_week():
    req = Request("https://api.sleeper.app/v1/state/nfl",headers={"User-Agent":"DieNasty-Weekly/1.0"})
    with urlopen(req,timeout=25) as r:
        state = json.load(r)
    return max(1,int(state["week"])-1)

def build():
    if not BASE or not KEY:
        print("Supabase credentials missing; NFL cards will use matching verified snapshot only")
        return
    week = read_week()
    sample = get("nfl_player_game",{"select":"gsis_id","season":"eq."+str(SEASON),"week":"eq."+str(week),"limit":"300"})
    if len(sample) < 200:
        print("NFL game data incomplete: no new snapshot saved")
        return
    metric_specs=[
        ("targets","THE TARGET VACUUM","receiving"),
        ("carries","WORKLOAD LANDLORD","rushing"),
        ("passing_tds","QUARTERBACK APOCALYPSE","passing")
    ]
    cards=[]
    for metric,label,kind in metric_specs:
        rows=get("nfl_player_game",{"select":"gsis_id,team,opponent,targets,receptions,receiving_yards,carries,rushing_yards,rushing_tds,attempts,completions,passing_yards,passing_tds","season":"eq."+str(SEASON),"week":"eq."+str(week),"order":metric+".desc","limit":"12"})
        row=next((r for r in rows if number(r.get(metric))>0),None)
        if not row: continue
        people=get("nfl_players",{"select":"display_name","gsis_id":"eq."+row["gsis_id"],"limit":"1"})
        if not people or not people[0].get("display_name"): continue
        if kind=="receiving":
            metrics=[["TARGETS",row["targets"]],["RECEPTIONS",row["receptions"]],["REC YARDS",row["receiving_yards"]],["TARGETS + CARRIES",number(row["targets"])+number(row["carries"])]]
            story=f'{row["targets"]} targets, {row["receptions"]} catches, and {row["receiving_yards"]} receiving yards. The volume is not a rumor.'
        elif kind=="rushing":
            metrics=[["CARRIES",row["carries"]],["TARGETS",row["targets"]],["RUSH YARDS",row["rushing_yards"]],["RUSH TD",row["rushing_tds"]]]
            story=f'{row["carries"]} carries, {row["targets"]} targets and {row["rushing_yards"]} rushing yards. The workload filed for overtime.'
        else:
            metrics=[["ATTEMPTS",row["attempts"]],["COMPLETIONS",row["completions"]],["PASS YARDS",row["passing_yards"]],["PASS TD",row["passing_tds"]]]
            story=f'{row["completions"]} completions on {row["attempts"]} attempts, {row["passing_yards"]} passing yards and {row["passing_tds"]} passing TDs. The defense should request paid leave.'
        cards.append({"name":people[0]["display_name"],"team":row["team"],"opponent":row["opponent"],"kind":kind,"label":label,"metrics":metrics,"story":story})
    if len(cards)!=3:
        print("Insufficient verified cards; preserving older snapshot")
        return
    out=Path("data") / f"nfl_week_{SEASON}_{week}.json"
    out.parent.mkdir(exist_ok=True)
    content={"season":SEASON,"week":week,"source":"Supabase nfl_player_game + nfl_players (daily sync)", "players":cards}
    out.write_text(json.dumps(content,indent=2)+"\n",encoding="utf-8")
    print("Verified nflverse snapshot:",str(out))

if __name__=="__main__":
    build()
