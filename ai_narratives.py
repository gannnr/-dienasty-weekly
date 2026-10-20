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


def fit_length(item):
    """Trim overlong AI prose at sentence boundaries; preserve the final punchline."""
    if not isinstance(item,dict):
        return item
    item=dict(item)
    fields=("film_room","bigger_conspiracy","next_episode")
    def word_total():
        return _words(" ".join(str(item.get(k,"")) for k in ("headline",)+fields))
    while word_total()>WORD_MAX:
        changed=False
        for key in sorted(("film_room","bigger_conspiracy"),key=lambda k:-_words(str(item.get(k,"")))):
            sentences=re.split(r"(?<=[.!?])\\s+(?=[A-Z0-9])",str(item.get(key,"")))
            if len(sentences)>1 and _words(" ".join(sentences[:-1]))>=30:
                item[key]=" ".join(sentences[:-1])
                changed=True
                break
        if not changed:
            break
    return item

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
      "absurd mock federal probes, grossly overconfident sports-take meltdowns, aura farming, "
      "catastrophic glazing, generational crashouts, NPC allegations, fictional press conferences, "
      "group-chat receipts, fake league scandals. Do NOT repeat canned jokes or slang across teams. "
      "Each recap must use minimum TWO named counted players with verified points, "
      "one specific meaningful advanced insight from countable lineup composition, positional "
      "output, three-week production trend, all-play results or schedule luck. "
      "Interpret the insight, not just list numbers. Choose a unique angle and headline per team. "
      "Ground all numerical statements and names ONLY in the provided fact sheets; never invent "
      "players, opponents, injuries, matchups, projections, rankings, or game context. "
      "Any fictional investigation is clearly satirical. No unexplained database field names "
      "like weekly_rank, season_record, or season_total_points in finished copy. "
      "Avoid bland phrases like maintain momentum, roster construction meeting discipline, "
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
                if fact and validate({"managers":[item]},[fact]):
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
                     "Use a distinct, punchy angle for each. Return complete JSON.",
                     "input":"Return JSON only. Verified facts and narrative history: "+
                     json.dumps({"season":2026,"week":week,"facts":group,
                                 "recent_narratives":history},ensure_ascii=False),
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
                    item=fit_length(raw_item)
                    fact=next((f for f in group if f["roster_id"]==item.get("roster_id")),None)
                    if fact and validate({"managers":[item]},[fact]):
                        accepted[item["roster_id"]]=item
                    else:
                        print("Rejected AI manager",item.get("roster_id"),
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
        if any(number not in allowed_numbers and len(number)>=2 for number in numbers):
            return False
        if "<" in prose or ">" in prose:
            return False
    return True

# Concurrent-writer integration verification.
