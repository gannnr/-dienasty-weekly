"""Authenticated Supabase fallback for weekly NFL Reality Check snapshots."""
import json
import os
import urllib.parse
import urllib.request

COLUMNS="gsis_id,team,opponent,completions,attempts,passing_yards,passing_tds,carries,rushing_yards,rushing_tds,receptions,targets,receiving_yards,receiving_tds"

def fetch(path, params):
    url=os.environ.get("SUPABASE_URL","").rstrip("/")
    key=os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_KEY") or ""
    if not url or not key:
        raise RuntimeError("Supabase fallback needs SUPABASE_URL and SUPABASE_SECRET_KEY repository secrets")
    target=url+"/rest/v1/"+path+"?"+urllib.parse.urlencode(params)
    request=urllib.request.Request(target,headers={"apikey":key,"Authorization":"Bearer "+key,"Accept":"application/json"})
    with urllib.request.urlopen(request,timeout=30) as response:
        return json.load(response)

def week_rows(week,season):
    games=fetch("nfl_player_game",{"select":COLUMNS,"season":"eq."+str(season),"week":"eq."+str(week),"season_type":"eq.REG","limit":"1000"})
    if len(games)<100:
        raise ValueError("Supabase NFL player-game data is incomplete: "+str(len(games))+" rows")
    ids=list(dict.fromkeys(g["gsis_id"] for g in games if g.get("gsis_id")))
    players={}
    for start in range(0,len(ids),60):
        batch=ids[start:start+60]
        rows=fetch("nfl_players",{"select":"gsis_id,display_name,nfl_position,espn_id","gsis_id":"in.("+",".join(batch)+")","limit":"100"})
        players.update({p["gsis_id"]:p for p in rows})
    normalized=[]
    for game in games:
        meta=players.get(game.get("gsis_id"),{})
        if meta.get("nfl_position") not in ("QB","RB","WR","TE"):
            continue
        if not meta.get("display_name"):
            continue
        normalized.append({**game,"position":meta["nfl_position"],"player_display_name":meta["display_name"],
                           "recent_team":game.get("team"),"opponent_team":game.get("opponent"),
                           "espn_id":meta.get("espn_id")})
    if len(normalized)<75:
        raise ValueError("Supabase NFL metadata coverage too low: "+str(len(normalized)))
    return normalized
