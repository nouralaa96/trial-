"""Root oversight: verify that this project did not change any prior research files."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path(__file__).resolve().parent
snapshot=json.loads((ROOT/'original_projects.json').read_text())
changed=[]
for name,expected in snapshot['sha256'].items():
    p=Path(name)
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
        changed.append(name)
result={'checked_at':datetime.now(timezone.utc).isoformat(),'files_checked':len(snapshot['sha256']),
        'all_unchanged':not changed,'changed_or_missing':changed}
(ROOT/'original_integrity.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
if changed:raise SystemExit(1)
