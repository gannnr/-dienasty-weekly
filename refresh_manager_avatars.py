"""Snapshot Sleeper portraits every September 8 for all weekly recaps."""
import json
import urllib.request
from pathlib import Path

league_id = "1312113845380083712"
request = urllib.request.Request(
    "https://api.sleeper.app/v1/league/" + league_id + "/users",
    headers={"User-Agent":"DieNasty-Avatar-Snapshot"}
)
with urllib.request.urlopen(request,timeout=30) as response:
    users=json.load(response)
if len(users)<10:
    raise RuntimeError("Incomplete Sleeper managers; preserving existing images")
photos={}
for user in users:
    uid=user["user_id"]
    avatar=user.get("avatar")
    if avatar:
        photos[str(uid)]="https://sleepercdn.com/avatars/thumbs/"+str(avatar)
Path("data").mkdir(exist_ok=True)
Path("data/manager_avatars.json").write_text(json.dumps(photos,indent=2)+"\n",encoding="utf-8")
print("Cached",len(photos),"Sleeper manager portraits")
