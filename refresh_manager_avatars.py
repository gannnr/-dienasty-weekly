"""Download and freeze actual Sleeper avatar image bytes every September 8."""
import json
import urllib.request
from pathlib import Path

LEAGUE_ID="1312113845380083712"
HEADERS={"User-Agent":"DieNasty-Avatar-Snapshot/2.0"}
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=30) as response:
        return response.read(),response.headers.get("Content-Type","")

raw,_=get("https://api.sleeper.app/v1/league/"+LEAGUE_ID+"/users")
users=json.loads(raw)
if len(users)!=10:
    raise RuntimeError("Expected exactly 10 members; refusing incomplete portrait update")
out=Path("assets/manager-avatars")
out.mkdir(parents=True,exist_ok=True)
manifest={}
for user in users:
    uid=str(user["user_id"])
    aid=user.get("avatar")
    if not aid:
        raise RuntimeError('Sleeper manager '+uid+' has no avatar; annual refresh cannot be completed')
    img,content_type=get("https://sleepercdn.com/avatars/"+str(aid))
    if not content_type.lower().startswith("image/") or len(img)<200:
        raise RuntimeError("Invalid image for Sleeper manager "+uid)
    extension=".png" if "png" in content_type else ".webp" if "webp" in content_type else ".jpg"
    filename=uid+extension
    (out/filename).write_bytes(img)
    manifest[uid]="assets/manager-avatars/"+filename
if len(manifest)!=10:
    raise RuntimeError("Only "+str(len(manifest))+" profile images available; keeping prior snapshot")
# Save league branding locally so the hero does not rely on remote CDN rendering.
league_raw,_=get("https://api.sleeper.app/v1/league/"+LEAGUE_ID)
league=json.loads(league_raw)
logo_id=league.get("avatar")
if logo_id:
    logo,mime=get("https://sleepercdn.com/avatars/"+str(logo_id))
    if not mime.lower().startswith("image/") or len(logo)<200:
        raise RuntimeError("Sleeper league logo response was not an image")
    Path("assets").mkdir(exist_ok=True)
    Path("assets/league-logo.png").write_bytes(logo)
Path("data").mkdir(exist_ok=True)
Path("data/manager_avatars.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
print("Downloaded and verified",len(manifest),"local Sleeper profile images")

# Refresh trigger for local league branding.
