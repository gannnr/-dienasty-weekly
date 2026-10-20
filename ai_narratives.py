"""Optional AI sports-desk editor for verified DieNasty weekly summaries.

Never exposes the API key in HTML. If not configured, returns no narratives.
"""
import json
import os
import re
import urllib.request
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

MODEL=os.environ.get("DIENASTY_AI_MODEL","gpt-5-mini")
WORD_MIN=180
WORD_MAX=230

def _words(text):
    return len(re.findall(r"\b[\w’'-]+\b",text))


def fit_length(item, fact=None):
    """Edit long reports deterministically while keeping a coherent closing punchline."""
    if not isinstance(item,dict):
        return item
    item=dict(item)
    fields=("film_room","bigger_conspiracy","next_episode")
    aliases={"weekly_allplay_wins":"all-play wins","weekly_allplay_losses":"all-play losses",
             "counted_best_ball":"best-ball lineup","top_three_share_pct":"top-three scoring share",
             "season_total_points":"season points","season_record":"season record",
             "weekly_rank":"weekly scoring rank","position_points":"positional scoring",
             "scoring_deserved_wins":"expected wins","season_points_rank":"season scoring rank",
             "schedule_luck_wins":"schedule luck","weekly_matchup_margin":"matchup margin",
             "top_best_ball_contributors":"top contributors","actual_wins":"actual wins"}
    for key in fields:
        value=str(item.get(key,""))
        for old,new in aliases.items():
            value=value.replace(old,new)
        item[key]=value
    def total():
        return _words(" ".join(str(item.get(k,"")) for k in ("headline",)+fields))
    if fact:
        allowed=set(re.findall(r"\d+(?:\.\d+)?",json.dumps(fact)))
        for key in fields:
            sentences=re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])",item[key])
            clean=[]
            for sentence in sentences:
                nums=re.findall(r"(?<!\w)\\d+(?:\.\d+)?",sentence)
                unknown=[n for n in nums if len(n)>=2 and n not in allowed]
                if unknown:
                    print("Removing unsupported numerical claim for",fact["roster_id"],"values:",unknown)
                else:
                    clean.append(sentence)
            if clean:
                item[key]=" ".join(clean)
    # Retain complete sentences only; never manufacture a period after a cut-off clause.
    for key,maximum in (("film_room",82),("bigger_conspiracy",72),("next_episode",42)):
        value=str(item.get(key,"")).strip()
        if _words(value)>maximum:
            sentences=re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])",value)
            kept=[]
            for sentence in sentences:
                if _words(" ".join(kept+[sentence]))>maximum:
                    break
                kept.append(sentence)
            if kept:
                item[key]=" ".join(kept)
    if total()>WORD_MAX:
        for key in ("film_room","bigger_conspiracy"):
            sentences=re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])",item[key])
            if total()<=WORD_MAX:
                break
            if len(sentences)>1:
                item[key]=" ".join(sentences[:-1])
    return item


VOICES=("SportsCenter meltdown","First Take argument","30 for 30 documentary","Film-room analyst","Postgame press conference","League group-chat correspondent","Mock financial analyst","Emergency broadcast","Championship committee","Sports radio caller")
BANNED_PHRASES=("satirical federal probe","league integrity committee","aura farming","npc allegation","schedule_luck_wins","weekly_allplay_wins","scoring_deserved_wins","season_total_points","season_points_rank","counted_best_ball","top_three_share_pct","weekly_matchup_margin","film room smells")
BEST_BALL_BAD_ADVICE=("start your","bench your","set your lineup","choose your starter","start the qb","play the qb","force correlation","pick the qb")
def editorial_issues(item,fact):
    prose=" ".join(str(item.get(k,"")) for k in ("headline","film_room","bigger_conspiracy","next_episode"))
    lower=prose.lower()
    issues=[]
    for phrase in BANNED_PHRASES+BEST_BALL_BAD_ADVICE:
        if phrase in lower: issues.append("banned phrase: "+phrase)
    for k in ("film_room","bigger_conspiracy","next_episode"):
        ending=str(item.get(k,"")).rstrip()
        if not ending.endswith((".","!","?")) or ending.endswith("…"):
            issues.append("incomplete ending: "+k)
    players=[p["name"].lower() for p in fact.get("counted_best_ball",{}).get("top_five",[]) if p.get("name")]
    if sum(name in lower for name in players)<2: issues.append("fewer than two counted players")
    return issues

def generate(week, facts):
    saved=Path("data/narratives")/f"2026_{week}.json"
    if saved.exists() and os.environ.get("REGENERATE_AI")!="1":
        cached=json.loads(saved.read_text(encoding="utf-8"))
        if validate(cached,facts):
            return cached
    token=os.environ.get("OPENAI_API_KEY")
    if not token:
        print("OPENAI_API_KEY not configured: using verified existing commentary")
        return None
    history=[]
    for previous in range(max(1,week-3),week):
        path=Path("data/narratives")/f"2026_{previous}.json"
        if path.exists():
            try:
                history.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError,ValueError):
                pass
    guide=(
      "You are GBSN DieNasty's unhinged ESPN SportsCenter and First Take writers room. "
      "Write 180-230 ORIGINAL words PER MANAGER, 55% rigorous fantasy journalism and "
      "45% wildly inventive Gen Alpha brainrot. Make the comedy relentless but varied: "
      "inventive sports-take meltdowns, absurd business analogies, surreal sports metaphors, "
      "generational crashouts, ridiculous fictional press conferences, dramatic documentaries, "
      "group-chat disasters, unexpected plot twists. Never use federal probes or aura farming. Do NOT repeat canned jokes or slang across teams. "
      "Each recap must use minimum TWO named counted players with verified points, "
      "one specific meaningful advanced insight from countable lineup composition, positional "
      "output, three-week production trend, all-play results or schedule luck. "
      "Explain the insight, then build a punchline FROM the actual football outcome. Choose a unique angle and headline per team. "
      "Ground all numerical statements and names ONLY in the provided fact sheets; never invent "
      "players, opponents, injuries, matchups, projections, rankings, or game context. "
      "This is BEST BALL: lineup scores automatically count; never give start/sit instructions. No unexplained database field names "
      "like weekly_rank, season_record, or season_total_points in finished copy. "
      "Never use mock subpoenas, dossiers, audits or generic legal accusations. Avoid bland phrases like maintain momentum, roster construction meeting discipline, "
      "remains competitive, or next week will be crucial. End with a savage original punchline. "
      "Three paragraphs: film_room 75-95 words, bigger_conspiracy 65-85 words, "
      "next_episode 35-50 words, plus sensational headline. "
      "Count all four fields together: 180 to 230 words. "
      "Recent narratives are for continuity but avoid repeating their jokes. "
      "Return valid JSON only. Schema: {\"managers\":[{\"roster_id\":number,\"headline\":string,"
      "\"film_room\":string,\"bigger_conspiracy\":string,\"next_episode\":string}]}; "
      "exactly one narrative for each supplied roster ID."
    )
    # Generate small batches to prevent truncated JSON and retain individually valid work.
    completed={}
    if saved.exists():
        try:
            old=json.loads(saved.read_text(encoding="utf-8"))
            for item in old.get("managers",[]):
                fact=next((f for f in facts if f["roster_id"]==item.get("roster_id")),None)
                if fact and validate({"managers":[item]},[fact]) and not editorial_issues(item,fact):
                    completed[item["roster_id"]]=item
        except (OSError,ValueError,AttributeError,TypeError):
            pass
    if os.environ.get("REGENERATE_AI")=="1":
        completed={}
    def write_group(group):
        accepted={}
        for attempt in range(2):
            payload={"model":MODEL,"instructions":guide+
                     " Generate ONLY the supplied managers. Every story must total 190-210 words. "
                     "Use the assigned voice and avoid any repeated federal-investigation jokes. No raw variable names or lineup-setting advice in this BEST BALL league. Return complete JSON.",
                     "input":"Return JSON only. Verified facts and narrative history: "+
                     json.dumps({"season":2026,"week":week,"facts":group,
                                 "recent_narratives":history,"assigned_voice":VOICES[group[0]["roster_id"]%len(VOICES)]},ensure_ascii=False),
                     "text":{"format":{"type":"json_object"}},
                     "reasoning":{"effort":"minimal"},
                     "max_output_tokens":8500}
            req=urllib.request.Request(
                "https://api.openai.com/v1/responses",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"},
                method="POST")
            try:
                with urllib.request.urlopen(req,timeout=75) as response:
                    result=json.load(response)
                output=result.get("output_text") or "".join(
                    p.get("text","") for item in result.get("output",[])
                    for p in item.get("content",[]) if p.get("type")=="output_text")
                if not output:
                    raise ValueError("Empty AI output "+str(result.get("incomplete_details")))
                candidate=json.loads(output)
                batch=candidate.get("managers",[])
                for raw_item in batch:
                    fact=next((f for f in group if f["roster_id"]==raw_item.get("roster_id")),None)
                    item=fit_length(raw_item,fact)
                    if fact and validate({"managers":[item]},[fact]):
                        accepted[item["roster_id"]]=item
                    else:
                        print("Rejected AI manager",item.get("roster_id"),"editorial issues:",editorial_issues(item,fact) if fact else ["missing facts"],
                              "word count",_words(" ".join(str(item.get(k,"")) for k in
                               ("headline","film_room","bigger_conspiracy","next_episode"))))
                group=[f for f in group if f["roster_id"] not in accepted]
                if not group:
                    break
            except Exception as error:
                detail=str(error)[:250]
                if hasattr(error,"read"):
                    try:
                        detail=str(json.loads(error.read().decode("utf-8")).get("error",{}).get("message",detail))[:250]
                    except (ValueError,UnicodeError):
                        pass
                print("AI small-batch attempt",attempt+1,"failed:",detail)
            if group and attempt<1:
                time.sleep(1)
        return accepted
    batches=[[f for f in facts[i:i+1] if f["roster_id"] not in completed] for i in range(0,len(facts),1)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(write_group,b) for b in batches if b]
        for future in as_completed(futures):
            completed.update(future.result())
            saved.parent.mkdir(parents=True,exist_ok=True)
            saved.write_text(json.dumps({"managers":list(completed.values())},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("AI editor accepted",len(completed),"of",len(facts),"manager stories")
    return {"managers":list(completed.values())} if completed else None

def validate(data,facts):
    if not isinstance(data,dict) or not isinstance(data.get("managers"),list):
        return False
    items=data["managers"]
    allowed={int(row["roster_id"]):row for row in facts}
    if len(items)!=len(allowed) or len(set(x.get("roster_id") for x in items if isinstance(x,dict)))!=len(allowed):
        return False
    headlines=set()
    for item in items:
        if not isinstance(item,dict) or item.get("roster_id") not in allowed:
            return False
        fields=["headline","film_room","bigger_conspiracy","next_episode"]
        if any(not isinstance(item.get(field),str) or not item[field].strip() for field in fields):
            return False
        if item["headline"].lower().strip() in headlines:
            return False
        headlines.add(item["headline"].lower().strip())
        prose=" ".join(item[field] for field in fields)
        if not WORD_MIN<=_words(prose)<=WORD_MAX:
            return False
        # Numeric facts (including player points and rankings) must come from the sheet.
        # Reject ungrounded multi-digit figures; single-digit numbers may be rhetorical.
        allowed_numbers=set(re.findall(r"\d+(?:\.\d+)?",json.dumps(allowed[item["roster_id"]])))
        numbers=re.findall(r"(?<!\w)\d+(?:\.\d+)?",prose)
        unknown=[number for number in numbers if len(number)>=2 and not any(
            abs(float(number)-float(allowed_value))<0.005
            for allowed_value in allowed_numbers)]
        if unknown:
            print("Manager",item["roster_id"],"unverified figures:",unknown)
            return False
        if "<" in prose or ">" in prose:
            return False
    return True

# Concurrent-writer integration verification.
