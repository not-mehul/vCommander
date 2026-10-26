"""Compare vCommander's endpoint registry with recorded Command web calls.

Usage: python tools/live/compare.py <recording.json|file.har> [...]

Recordings are HAR files or the JSON logs written by web/record.js. For each
registry endpoint it reports whether the web app made the same call, and
differences in method, service (subdomain) and payload key paths. Values are
never printed. Full results go to $LIVE_OUT/compare.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apis.endpoints import API_GATEWAY_SUBDOMAIN, ENDPOINTS  # noqa: E402

OUT = Path(os.environ.get("LIVE_OUT", Path.home() / ".vcommander-live"))
_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27}", re.I)


def keypaths(value, prefix: str = "") -> set[str]:
    """Flattened key paths of a JSON value ("a.b", "a[].c")."""
    out: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            out.add(path)
            out |= keypaths(item, path)
    elif isinstance(value, list):
        for item in value[:5]:
            out |= keypaths(item, prefix + "[]")
    return out


def _short(keys: list[str], limit: int = 8) -> str:
    """Top-level-first key list, trimmed for the console (compare.json has all)."""
    keys = sorted(keys, key=lambda k: (k.count(".") + k.count("[]"), k))
    more = f" +{len(keys) - limit} more" if len(keys) > limit else ""
    return ", ".join(keys[:limit]) + more


def load(path: str):
    """Yield (method, host, path, body, status) for each recorded request."""
    data = json.load(open(path))
    if isinstance(data, dict) and "log" in data:
        for entry in data["log"]["entries"]:
            req = entry["request"]
            m = re.match(r"https://([^/]+)(/[^?]*)", req["url"])
            if m:
                body = (req.get("postData") or {}).get("text") or ""
                yield req["method"], m[1], m[2], body, entry["response"]["status"]
    else:
        for call in data:
            yield call["method"], call["host"], call["path"].split("?")[0], call[
                "body"
            ], call["status"]


def main(files: list[str]) -> None:
    index = [
        (key, ep, re.compile("^" + re.sub(r"\\\{\w+\\\}", "[^/]+", re.escape(ep.path)) + "$"))
        for key, ep in ENDPOINTS.items()
    ]
    seen = defaultdict(list)
    unmatched = set()
    for fn in files:
        for method, host, path, body, status in load(fn):
            m = re.match(r"^/__v/[^/]+/(.*)$", path)
            if not m or method == "OPTIONS":
                continue
            hits = [(key, ep) for key, ep, rx in index if rx.match(m[1])]
            service = host.split(".")[0]
            if not hits:
                unmatched.add((method, service, _ID.sub("{id}", m[1])))
            for key, _ in hits:
                seen[key].append((method, service, body, status))

    report = {}
    for key, ep in ENDPOINTS.items():
        rows = seen.get(key, [])
        entry = {"method": ep.method, "service": ep.subdomain, "seen": len(rows)}
        if rows:
            web_keys: set[str] = set()
            for _, _, body, _ in rows:
                try:
                    web_keys |= keypaths(json.loads(body))
                except ValueError:
                    pass
            reg_keys = keypaths(ep.payload)
            entry.update(
                web_methods=sorted({r[0] for r in rows}),
                web_services=sorted({r[1] for r in rows}),
                statuses=sorted({r[3] for r in rows}),
                only_vcommander=sorted(reg_keys - web_keys),
                only_web=sorted(web_keys - reg_keys),
            )
        report[key] = entry

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "compare.json").write_text(
        json.dumps({"endpoints": report, "unmatched_web_calls": sorted(unmatched)}, indent=1)
    )
    hit = [k for k, e in report.items() if e["seen"]]
    print(f"{len(hit)}/{len(ENDPOINTS)} registry endpoints seen in recordings")
    for key in hit:
        e = report[key]
        flags = []
        if e["web_methods"] != [e["method"]]:
            flags.append(f"method web={e['web_methods']} vc={e['method']}")
        if e["service"] != API_GATEWAY_SUBDOMAIN and e["web_services"] != [e["service"]]:
            flags.append(f"service web={e['web_services']} vc={e['service']}")
        if e["only_vcommander"]:
            flags.append(f"vc-only keys={_short(e['only_vcommander'])}")
        if e["only_web"]:
            flags.append(f"web-only keys={_short(e['only_web'])}")
        print(f"  {key:45} x{e['seen']:<3} {' | '.join(flags) or 'OK'}")
    print(f"{len(unmatched)} web calls match no registry endpoint (see compare.json)")


if __name__ == "__main__":
    main(sys.argv[1:])
