"""Validate DieNasty's generated report before GitHub Pages publication."""
from pathlib import Path
import re
import sys

page = Path("index.html").read_text(encoding="utf-8")
source = Path("generate_weekly.py").read_text(encoding="utf-8")
checks = {
    "weekly headline": bool(re.search(r"WEEK\s+\d+<br>IS UNWELL", page)),
    "manager cards": page.count('<details class="card">') == 10,
    "schedule justice chart": '<svg viewBox="0 0 600 515"' in page,
    "all manager player contributors": page.count("Top automatic best-ball scorers:") == 10,
    "season comparisons": "The record is lying" in page,
    "weekly scoring": "Who ate?" in page,
    "weekly awards": "Weekly hardware" in page,
    "correct league": "1312113845380083712" in page,
    "expected wins math": "expected_wins[rid]" in source,
    "valid HTML": page.strip().endswith("</html>"),
}
for check, passed in checks.items():
    print(("PASS" if passed else "FAIL") + " " + check)
if not all(checks.values()):
    sys.exit("Generated page failed quality checks: old live site remains untouched.")
