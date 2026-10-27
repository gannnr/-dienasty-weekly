"""Validate DieNasty's generated report before GitHub Pages publication."""
from pathlib import Path
import json
import re
import sys

page = Path("index.html").read_text(encoding="utf-8")
source = Path("generate_weekly.py").read_text(encoding="utf-8")
checks = {
    "weekly headline": bool(re.search(r"WEEK\s+\d+<br>IS UNWELL", page)),
    "manager cards": page.count('<details class="card">') == 10,
    "schedule justice chart": '<svg viewBox="0 0 600 515"' in page,
    "all manager player contributors": page.count("Top automatic best-ball scorers:") == 10,
    "lucky dawg rankings": "Total Season Lucky Dawg Rankings" in page,
    "weekly all-play": "All-Play Record" in page,
    "removed redundant standings": "The record is lying" not in page,
    "lucky dawg rank columns": all(text in page for text in ["Expected wins","Actual wins","Luck"]),
    "weekly awardz": "Weekly Awardz" in page,
    "ten award cards": page.count("data-award-id=") == 10,
    "ten unique awards": len(set(re.findall(r'data-award-id="([^"]+)"',page))) == 10,
    "one award per manager": len(set(re.findall(r'data-manager-id="([^"]+)"',page))) == 10,
    "retired redundant sections": "Weekly hardware" not in page and "The league is cooked" not in page,
    "correct league": "1312113845380083712" in page,
    "expected wins math": "expected_wins[rid]" in source,
    "valid HTML": page.strip().endswith("</html>"),
}
match = re.search(r"WEEK\s+(\d+)<br>IS UNWELL", page)
if match:
    snapshot = Path("data") / ("nfl_week_2026_" + match.group(1) + ".json")
    checks["NFL Reality Check snapshot exists"] = snapshot.is_file()
    checks["NFL Reality Check section"] = "nfl reality check" in page.lower()
    if snapshot.is_file():
        data=json.loads(snapshot.read_text(encoding="utf-8"))
        players=data.get("players",[])
        checks["NFL snapshot matches report week"] = data.get("week")==int(match.group(1)) and data.get("season")==2026
        checks["three verified NFL player cards"] = len(players)==3 and all(p.get("name") in page and len(p.get("metrics",[]))==4 for p in players)
    else:
        checks["three verified NFL player cards"] = False
else:
    checks["NFL Reality Check snapshot exists"] = False
for check, passed in checks.items():
    print(("PASS" if passed else "FAIL") + " " + check)
if not all(checks.values()):
    sys.exit("Generated page failed quality checks: old live site remains untouched.")

# Week 7 NFL Reality Check verification after corrected snapshot validation.
