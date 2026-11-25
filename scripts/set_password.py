"""Set the dashboard password on Rauf's EXISTING Supabase user (admin API).

  python scripts/set_password.py

Asks for the password with getpass (not echoed, never printed or logged).
Only touches the user with the owner ID that RLS is keyed to; never creates a user.
"""
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

OWNER_ID = "46430da4-5073-4b08-aaaa-a41ecb1e648d"


def admin(method, path, body=None):
    base, key = db._env()
    url = base.replace("/rest/v1/", "/auth/v1/") + path
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"apikey": key, "Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("msg") or json.loads(e.read()).get("message")
        except Exception:
            msg = ""
        sys.exit(f"Admin API error {e.code} {msg or ''}".strip())


def main():
    user = admin("GET", f"admin/users/{OWNER_ID}")
    if user.get("id") != OWNER_ID:
        sys.exit("Owner user not found. Nothing changed.")
    print(f"User found: {user.get('email', '?')} (owner ID matches)")
    pw = getpass.getpass("New password (min 12 characters, not shown): ")
    if len(pw) < 12:
        sys.exit("Too short: use at least 12 characters. Nothing changed.")
    if getpass.getpass("Repeat password: ") != pw:
        sys.exit("Passwords don't match. Nothing changed.")
    admin("PUT", f"admin/users/{OWNER_ID}", {"password": pw})
    del pw
    print("Password set. Sign in at https://research-dashboard-bice.vercel.app/login")


if __name__ == "__main__":
    main()
