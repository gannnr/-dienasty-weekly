"""Optional AI sports-desk editor for verified DieNasty weekly summaries.

Never exposes the API key in HTML. If not configured, returns no narratives.
"""
import json
import os
import re
import urllib.request
from pathlib import Path

MODEL=os.environ.get("DIENASTY_AI_MODEL","gpt-5-mini")
WORD_MIN=130
WORD_MAX=180

def _words(text):
    return len(re.findall(r"\b[\w’'-]+\b",text))

def generate(week, facts):
    saved=Path("data/narratives")/f"2026_{week}.json"
    if saved.exists():
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
      "You are DieNasty's ESPN/SportsCenter fantasy-football editorial team, "
      "with 65% credible sportscaster analysis and 35% extreme Gen Alpha brainrot. "
      "Write an original 130-180 word recap PER MANAGER, comprised of headline, "
      "The Film Room, The Bigger Conspiracy, and Next Episode. Be savage, "
      "funny, unpredictable, and distinct for every team. Refer to player contributions "
      "and season trajectory. Change the framing, opening technique, and punchlines "
      "between teams and weeks. Never invent statistics, player names, games, "
      "injuries, or opponents. You may use only facts in the supplied fact sheets. "
      "No percentages or derived metrics unless in those sheets. "
      "The next episode section should be speculative, not assert future results. "
      "Respond with a JSON object: {\"managers\":[{\"roster_id\":number,"
      "\"headline\":string,\"film_room\":string,\"bigger_conspiracy\":string,"
      "\"next_episode\":string}]}. Exactly one entry for each supplied roster ID."
    )
    payload={"model":MODEL,"instructions":guide,
             "input":json.dumps({"season":2026,"week":week,"facts":facts,"recent_narratives":history},ensure_ascii=False),
             "text":{"format":{"type":"json_object"}},
             "max_output_tokens":8000}
    req=urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req,timeout=120) as response:
            result=json.load(response)
        output=result.get("output_text")
        if not output:
            output="".join(part.get("text","") for item in result.get("output",[]) for part in item.get("content",[]) if part.get("type")=="output_text")
        narratives=json.loads(output)
        if not validate(narratives,facts):
            raise ValueError("AI prose failed structural or factual safeguards")
    except Exception as error:
        detail=str(error)[:250]
        if hasattr(error,"read"):
            try:
                body=json.loads(error.read().decode("utf-8"))
                detail=str(body.get("error",{}).get("message",detail))[:350]
            except (ValueError,UnicodeError):
                pass
        print("AI editor unavailable or failed validation, retaining original manager summaries:",detail)
        return None
    saved.parent.mkdir(parents=True,exist_ok=True)
    saved.write_text(json.dumps(narratives,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return narratives

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
