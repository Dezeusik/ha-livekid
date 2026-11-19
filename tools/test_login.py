#!/usr/bin/env python3
"""Test logowania do LiveKid bez Home Assistanta (tylko biblioteka standardowa).
    curl -sL https://raw.githubusercontent.com/Dezeusik/ha-livekid/main/tools/test_login.py | python3 - twoj@email
Hasło wpisujesz lokalnie; trafia tylko do API LiveKid."""
import getpass, json, sys, urllib.error, urllib.request
from datetime import date

BASE = "https://pl.api.api-livekid-prod.com/"
H = {"Accept": "application/json, text/plain, */*", "Content-Type": "application/json",
     "Origin": "https://app.livekid.com", "Referer": "https://app.livekid.com/"}


def call(method, path, body=None, jwt=None):
    req = urllib.request.Request(BASE + path, method=method, headers={**H, **({"Authorization": f"Bearer {jwt}"} if jwt else {})},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


email = sys.argv[1] if len(sys.argv) > 1 else input("E-mail: ")
status, data = call("POST", "v1/accounts/login", {"mail": email.strip().lower(), "password": getpass.getpass("Hasło do LiveKid: ")})
print("Logowanie:", status)
if status != 200:
    sys.exit(f"Odpowiedź: {data}")
for r in [x for x in data.get("roles", []) if x.get("type") == "parent"]:
    s, day = call("GET", f"v1/presence/{date.today().isoformat()}/{r['kid']}", jwt=r["jwt"])
    m = lambda v: f"{v // 60:02d}:{v % 60:02d}" if isinstance(v, int) else "-"
    print(f"- {r.get('kid_name')} ({r.get('school_name')}): obecność HTTP {s}, przyszedł {m(day.get('in')) if s == 200 else '?'}, "
          f"odebrany {m(day.get('out')) if s == 200 else '?'}")
print("OK – integracja powinna działać.")
