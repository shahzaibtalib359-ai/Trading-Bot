"""Quick setup: create user + license + subscription for localhost testing."""
import urllib.request
import json

BASE = 'http://127.0.0.1:8012/api'


def post(url, data, headers=None):
    h = {'Content-Type': 'application/json'}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=h, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.request.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


# ── 1. Register user ──
print("=== Setup: SS Traderz User ===\n")
status, reg = post(f'{BASE}/auth/register', {'username': 'PMLS', 'email': 'pmls@trader.com', 'password': 'trader123'})
if status == 200:
    print("User registered OK!")
elif 'already' in str(reg).lower() or status == 409 or status == 400:
    print("User already exists - OK")
else:
    print(f"Register: {status} - {reg}")

# ── 2. Admin login ──
status, admin = post(f'{BASE}/admin/login', {'password': '07862433'})
admin_token = admin['token']
print(f"Admin login OK")

# ── 3. Get users ──
users = get(f'{BASE}/admin/users', {'X-Admin-Token': admin_token})
pmls = next((u for u in users if u['username'] == 'PMLS'), None)
if not pmls:
    print("ERROR: User PMLS not found!")
    exit(1)

uid = pmls['id']
print(f"Found user: id={uid} username={pmls['username']} active={pmls['is_active']}")

# ── 4. Set subscription ──
status, sub = post(f'{BASE}/admin/users/{uid}/subscription', {'days': 365},
                   {'X-Admin-Token': admin_token})
print(f"Subscription set: {sub}")

# ── 5. Create fresh license ──
status, lic = post(f'{BASE}/admin/licenses', {'owner': 'PMLS', 'days': 365},
                   {'X-Admin-Token': admin_token})
lic_key = lic.get('key', '')
print(f"License key: {lic_key}")

# ── 6. Test license-login ──
status, login = post(f'{BASE}/auth/license-login', {'username': 'PMLS', 'license_key': lic_key})
print(f"\n=== License Login Test ===")
print(f"Status: {status}")
if status == 200:
    print(f"LOGIN SUCCESS!")
    print(f"  Token    : {login.get('token', '')[:30]}...")
    print(f"  User ID  : {login.get('user_id')}")
    print(f"  Username : {login.get('username')}")
    print(f"  Expires  : {login.get('expires_at')}")
    print(f"\n=== APP LOGIN CREDENTIALS ===")
    print(f"  Username    : PMLS")
    print(f"  License Key : {lic_key}")
    print(f"\n  Open browser: http://localhost:5173")
    print(f"  Enter above credentials to login!")
else:
    print(f"Login failed: {login}")
