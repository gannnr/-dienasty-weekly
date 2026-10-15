"""Deterministic, one-per-manager DieNasty Weekly Awardz engine."""
import html, json
from pathlib import Path

AWARDS = [
 ("nuke","💣","Nuclear Warhead"),("execution","🪓","Public Execution"),
 ("cardiac","🫀","Cardiac Arrest"),("merchant","🎰","Schedule Merchant"),
 ("carry","🚀","One-Man Carry Job"),("cursed","💀","Cursed by the Algorithm"),
 ("stinker","🗑️","Generational Stinker"),("titanic","🚢","Titanic Performance"),
 ("almost","🪦","Almost Had It"),("brick","🧱","Brick Squad"),
 ("fraud","🚨","Fraud Watch"),("revival","🧟","Back From the Dead"),
 ("fall","📉","Fall From Grace"),("underdawg","🐕","Underdawg Energy"),
 ("boss","👑","Final Boss"),("depth","🧠","Depth Merchant"),
 ("spikes","🎆","Spike Week Demon"),("frozen","🧊","Frozen Assets"),
 ("qbs","🐐","QB Factory"),("emergency","🏥","Emergency Room FC"),
]

def assign(week,teams,scores,matchups,season_wins,expected_wins,season_points,weekly_history,lineups,player_names=None,player_positions=None):
    """For each of 10 managers select one distinct category maximizing verified fit, drama and novelty."""
    ids=sorted(teams)
    if len(ids)!=10: raise ValueError("Weekly Awardz requires exactly 10 distinct managers")
    n=len(ids)
    previous=weekly_history.get(week-1,{})
    previous_scores={rid:float(previous[rid]) for rid in ids} if len(previous)==n else {}
    old_ranks={rid:1+sum(s>previous_scores[rid] for s in previous_scores.values()) for rid in ids} if previous_scores else {}
    current_ranks={rid:1+sum(s>scores[rid] for s in scores.values()) for rid in ids}
    metrics={rid:{} for rid in ids}
    eligible={rid:{} for rid in ids}
    def offer(rid,award,value,narrative):
        if value is not None:
            metrics[rid][award]=float(value)
            eligible[rid][award]=narrative
    for rid in ids:
        score=float(scores[rid]); rival,ours,theirs=matchups[rid]
        won=ours>theirs;lost=ours<theirs
        margin=abs(ours-theirs)
        ranking=current_ranks[rid]
        net=float(season_wins[rid]-expected_wins[rid])
        lineup=lineups.get(rid) or []
        pts=sorted((float(p[1]),str(p[0])) for p in lineup)[::-1]
        peak=pts[0][0] if pts else None
        topthree=sum(v for v,_ in pts[:3])
        offer(rid,"nuke",score,f"{score:.2f} points. The scoreboard just filed a workers comp claim.")
        if won:
            offer(rid,"execution",margin,f"Won by {margin:.2f}. The opponent has been placed in witness protection.")
            offer(rid,"cardiac",1/(.1+margin),f"Survived by {margin:.2f} points. Their Apple Watch called 911.")
            offer(rid,"merchant",ranking,f"Won despite ranking #{ranking} in points. The schedule is their franchise QB.")
        if lost:
            offer(rid,"cursed",score,f"Scored {score:.2f} and STILL lost. The universe is farming engagement.")
            offer(rid,"almost",1/(.1+margin),f"Lost by {margin:.2f}. A generational almost-moment.")
        offer(rid,"stinker",-score,f"Scored {score:.2f}. The offense has been reported missing.")
        offer(rid,"fraud",net,f"{season_wins[rid]} real wins vs {expected_wins[rid]:.2f} deserved. Differential: {net:+.2f}. Schedule glazing is undefeated.")
        offer(rid,"boss",float(season_points[rid]) if season_wins[rid]>week/2 else None,f"{season_points[rid]:.2f} season points with a winning record. Final boss health bar detected.")
        if old_ranks:
            old=old_ranks[rid]
            change=old-ranking
            offer(rid,"revival",change if change>0 else None,f"Jumped from #{old} to #{ranking} in scoring. Lazarus got the Wi-Fi password.")
            offer(rid,"fall",-change if change<0 else None,f"Fell from #{old} to #{ranking}. The wheels left the group chat.")
            delta=score-previous_scores[rid]
            offer(rid,"titanic",-delta if delta<0 else None,f"Down {abs(delta):.2f} points from last week. Iceberg speedrun.")
        if won:
            underdog=int(season_points.get(rival,0)>season_points[rid])
            if underdog:
                offer(rid,"underdawg",float(season_points[rival]-season_points[rid]),f"Beat {html.escape(teams[rival])}, a higher-scoring season team. The upset department is hiring.")
        if pts and score>0:
            share=peak/score
            offer(rid,"carry",share,f"Top scorer contributed {share:.0%} of team points. Everybody else rode shotgun.")
            depth=max(0,(score-topthree)/score)
            offer(rid,"depth",depth,f"{depth:.0%} of points came from outside the top three. Actual bench-industrial complex.")
            spikes=sum(v>=20 for v,_ in pts)
            offer(rid,"spikes",spikes,f"{spikes} counted players reached 20+ points. Slot-machine simulator activated.")
            offer(rid,"brick",-topthree,f"Top three produced {topthree:.2f} points. Stars on airplane mode.")
            # Only counted player scores: no guesses about inactivity or roster health.
            qbs=[v for v,p in pts if player_positions and player_positions.get(p)=="QB"]
            if qbs:offer(rid,"qbs",sum(qbs),f"Counted QBs combined for {sum(qbs):.2f}. Quarterback factory running overtime.")
    # Frozen Assets / Emergency Room FC require separate verified active/inactive feeds.
    # They remain in the official 20-award catalog but are never spuriously awarded.
    # Rank each metric among its eligible managers; reward data strength and drama.
    candidate={}
    for key,emoji,title in AWARDS:
        pool=[(rid,metrics[rid][key]) for rid in ids if key in metrics[rid]]
        if not pool:continue
        lo=min(v for _,v in pool);hi=max(v for _,v in pool)
        for rid,v in pool:
            norm=(v-lo)/(hi-lo) if hi>lo else .5
            # Strength of statistical fit 60%, drama 25%, variety 15%.
            fit=60*norm
            drama=25*max(0,min(1,(abs(v)/(abs(v)+2) if key in ("fraud","almost","cardiac") else norm)))
            history=Path("data")/"awardz"
            recent=0
            for past in range(max(1,week-3),week):
                file=history/f"2026_{past}.json"
                if file.exists():
                    try:
                        payload=json.loads(file.read_text(encoding="utf-8"))
                        recent+=any(a.get("roster_id")==rid and a.get("award_id")==key for a in payload.get("awards",[]))
                    except (ValueError,OSError):pass
            novelty=15 if recent==0 else max(-25,15-25*recent)
            candidate[(rid,key)]=(fit+drama+novelty,eligible[rid][key])
    # Global DP across manager bitmasks: each award at most once, each manager exactly once.
    dp={0:(0.0,[])}
    for key,emoji,title in AWARDS:
        nxt=dict(dp)
        for mask,(score,choices) in dp.items():
            for i,rid in enumerate(ids):
                if mask>>i&1 or (rid,key) not in candidate:continue
                nm=mask|(1<<i)
                value=score+candidate[(rid,key)][0]
                if nm not in nxt or value>nxt[nm][0]:
                    nxt[nm]=(value,choices+[(rid,key)])
        dp=nxt
    if (1<<n)-1 not in dp:raise ValueError("Cannot find 10 valid distinct awards")
    assignments=dp[(1<<n)-1][1]
    by_key={a[0]:a for a in AWARDS}
    output=[]
    for rid,key in assignments:
        emoji,title=by_key[key][1:]
        score,_=candidate[(rid,key)]
        output.append({"roster_id":rid,"name":teams[rid].strip(),"award_id":key,"award":title,"emoji":emoji,"strength":round(score,3),"evidence":eligible[rid][key]})
    output.sort(key=lambda x:(-x["strength"],x["name"]))
    if len(output)!=10 or len({v["award_id"] for v in output})!=10 or len({v["roster_id"] for v in output})!=10:
        raise AssertionError("Weekly Awardz uniqueness failure")
    return output

def render(awards):
    sections=['<h2>🏆 Weekly Awardz</h2><p class="small">Ten managers. Ten different trophies. Data-backed chaos, most dramatic first.</p><div class="two">']
    for a in awards:
        sections.append('<div class="card" data-award-id="'+html.escape(a["award_id"])+'" data-manager-id="'+str(a["roster_id"] )+'"><span class="label">'+html.escape(a["emoji"]+" "+a["award"])+'</span><h3>'+html.escape(a["name"])+'</h3><p>'+a["evidence"]+'</p></div>')
    sections.append('</div>')
    return ''.join(sections)
