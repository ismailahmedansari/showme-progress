"""Builds the public ShowMe-Bench progress page (GitHub Actions; also used locally by the owner).

Inputs in this repo, counts only:
  reports/<X|Y|Z>.json  {"lines": ["SHOWME-S2 code=X role=primary products=5/24 requests=21/96 ls_minutes=80
                                    other_minutes=45 at=2026-10-20T18:02", ...]}   written by each member's kit
  gate.json             {"members": {"X": {"primary_locked": 0, "adjudication_locked": 0, ...}, ...},
                         "updated_at": "..."}                                         written by the owner
A line that is not exactly a counts line is skipped (a fixed warning code in the Actions log, never the rejected text)
and never reaches the page. The workflow runs THIS file from a pinned commit (SITE_REF in the workflow), so a token
that can write reports cannot change the code that builds the page.

usage: python build.py --data <data repo dir> --site <site code dir> --out <out_dir>
       python build.py <out_dir>          # local: data and site are this folder
"""
import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARK = "/*SNAPSHOT*/null/*END*/"
CODES = ("X", "Y", "Z")
LINE = re.compile(r"^SHOWME-S2 code=(?P<code>[XYZ]) role=(?P<role>primary|adjudication|setup) "
                  r"products=(?P<p>\d{1,3})/(?P<pt>\d{1,3}) requests=(?P<r>\d{1,3})/(?P<rt>\d{1,3}) "
                  r"ls_minutes=(?P<ls>\d{1,5}) other_minutes=(?P<om>\d{1,5}) at=(?P<at>\d{4}-\d\d-\d\dT\d\d:\d\d)$")
LIMITS = dict(primary=(24, 96), adjudication=(24, 96), setup=(0, 0))   # S2 design v2 (TEAM_PLAN v0.4)
GATE_CAP = dict(primary_issued=24, primary_locked=24, adjudication_issued=24, adjudication_locked=24)
ROLE_OF = dict(X="primary", Z="primary", Y="adjudication")
GATE_KEYS = ("primary_issued", "primary_locked", "adjudication_issued", "adjudication_locked")


class Invalid(ValueError):
    pass


def parse(line, now=None):
    if not isinstance(line, str) or len(line) > 200:
        raise Invalid("E_TYPE")
    m = LINE.match(line.strip())
    if not m:
        raise Invalid("E_FORMAT")
    d = m.groupdict()
    p, pt, r, rt = (int(d[k]) for k in ("p", "pt", "r", "rt"))
    lp, lr = LIMITS[d["role"]]
    if not (0 <= p <= pt <= lp and 0 <= r <= rt <= lr):
        raise Invalid("E_RANGE")
    if int(d["ls"]) > 60 * 60 or int(d["om"]) > 60 * 60:
        raise Invalid("E_MINUTES")
    if (p == pt and pt and r != rt) or r < p:
        raise Invalid("E_COUNTS")
    try:
        at = datetime.datetime.strptime(d["at"], "%Y-%m-%dT%H:%M")
    except ValueError:
        raise Invalid("E_DATE")
    if not datetime.datetime(2026, 10, 1) <= at <= (now or datetime.datetime.now()) + datetime.timedelta(days=1):
        raise Invalid("E_DATE_RANGE")
    return dict(code=d["code"], role=d["role"], products=p, products_total=pt, requests=r, requests_total=rt,
                ls_minutes=int(d["ls"]), other_minutes=int(d["om"]), at=d["at"])


def latest(reports):
    out = {}
    for rep in reports:
        k = (rep["code"], rep["role"])
        if k not in out or rep["at"] >= out[k]["at"]:
            out[k] = rep
    return out


def clean_gate(gate):
    """Only integer lock/issue counts per code survive; anything else is dropped."""
    out = {}
    members = gate.get("members") if isinstance(gate, dict) else None
    members = members if isinstance(members, dict) else {}
    for c in CODES:
        g = members.get(c) if isinstance(members.get(c), dict) else {}
        out[c] = {k: g[k] if type(g.get(k)) is int and 0 <= g[k] <= GATE_CAP[k] else 0 for k in GATE_KEYS}
    return out


def snapshot(reports, gate_members, now=None):
    """Role-aware: X/Z completion from primary, Y from adjudication; other minutes = max over a member's lines."""
    lat = latest(reports)
    members = {}
    for c in CODES:
        rows = {role: rep for (code, role), rep in lat.items() if code == c}
        work = rows.get(ROLE_OF[c])
        members[c] = dict(products=(work or {}).get("products", 0), requests=(work or {}).get("requests", 0),
                          ls_minutes=(work or {}).get("ls_minutes", 0),
                          other_minutes=max([r["other_minutes"] for r in rows.values()] or [0]),
                          reported_at=max([r["at"] for r in rows.values()] or [""]), **gate_members[c])
    return dict(members=members, updated_at=(now or datetime.datetime.now(datetime.timezone.utc)).isoformat())


def load_reports(folder, warn=print):
    reps = []
    for f in sorted(Path(folder).glob("*.json")):
        if f.stem not in CODES:
            warn("::warning::ignored a file in reports/ (only X.json, Y.json, Z.json are read)")
            continue
        try:
            data = json.loads(f.read_text())
            lines = data["lines"] if isinstance(data, dict) and isinstance(data.get("lines"), list) else None
            if lines is None or len(lines) > 3 or set(data) != {"lines"}:
                raise Invalid("E_SHAPE")
            for line in lines:
                rep = parse(line)
                if rep["code"] != f.stem:
                    raise Invalid("E_CODE")
                reps.append(rep)
        except Invalid as e:
            warn(f"::warning::skipped {f.stem}.json ({e})")
        except ValueError:
            warn(f"::warning::skipped {f.stem}.json (E_JSON)")
    return reps


def load_gate(path, warn=print):
    try:
        return clean_gate(json.loads(Path(path).read_text()) if Path(path).exists() else {})
    except ValueError:
        warn("::warning::gate.json is not valid JSON (E_GATE); lock counts shown as 0")
        return clean_gate({})


def build(out_dir, root=HERE, site=None):
    site = site or root
    snap = snapshot(load_reports(Path(root) / "reports"), load_gate(Path(root) / "gate.json"))
    t = (Path(site) / "template.html").read_text()
    if MARK not in t:
        raise SystemExit("template has no snapshot marker")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(t.replace(MARK, json.dumps(snap).replace("<", "\\u003c")))
    return snap


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--out" in a:
        s = build(a[a.index("--out") + 1], Path(a[a.index("--data") + 1]), Path(a[a.index("--site") + 1]))
    else:
        s = build(a[0] if a else "_site")
    print(json.dumps({c: {k: v for k, v in m.items() if k in ("products", "requests", "reported_at")}
                      for c, m in s["members"].items()}))
