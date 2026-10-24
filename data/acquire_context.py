"""Reacquire only the three pinned public mirror files, verifying frozen hashes.

This is optional: offline research rebuilds use the retained bytes. Run after
checking current managed environment network status and networking instructions.
No market-provider domains, authentication, proxy changes or paid APIs are used.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REVISION = "3dbea23c70cc2afbeeec8ac232c9ec72ac26ac21"
FILES = {
    "data/vix-daily.csv": "570e05630c9a5e7350d0c3dbe3acc58e793cb5248181ab0e949c121cc082fb83",
    "datapackage.json": "d2c56b6586d19762da81fe332650ec949f2a42c4d2a2228c59ad5b397bac1e64",
    "README.md": "a6803998768a1b636474c6ed1b4041e1d4193e4e019b84741638e23113a07bfd",
}


def main():
    policy_file = Path("/etc/codex/network-policy.json")
    if policy_file.exists():
        policy = json.loads(policy_file.read_text())
        http = policy.get("http_network_policy", {})
        allowed = {x.get("host") for x in http.get("egress_rules", [])}
        if policy.get("version") != 1 or (http.get("type") == "restricted" and "raw.githubusercontent.com" not in allowed):
            raise SystemExit("Current managed policy does not establish permission for this mirror")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = ROOT / "data/raw/reacquisition" / stamp
    target.mkdir(parents=True, exist_ok=False)
    records = []
    for relative, expected_hash in FILES.items():
        url = f"https://raw.githubusercontent.com/datasets/finance-vix/{REVISION}/{relative}"
        record = {"url": url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "tls_verification": True}
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read()
            digest = hashlib.sha256(content).hexdigest()
            if urllib.parse.urlsplit(response.url).hostname != "raw.githubusercontent.com" or digest != expected_hash:
                raise ValueError("Pinned source changed or unexpected redirect")
            path = target / Path(relative).name
            path.write_bytes(content)
            record.update(http_status=response.status, final_url=response.url, bytes=len(content), sha256=digest, path=str(path.relative_to(ROOT)))
        records.append(record)
    (target / "retrieval_evidence.json").write_text(json.dumps({"revision": REVISION, "records": records}, indent=2) + "\n")
    print(target)


if __name__ == "__main__":
    main()
