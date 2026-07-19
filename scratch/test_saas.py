import urllib.request
import json
import random
import time

BASE_URL = "http://127.0.0.1:8012/api"

def make_request(url, method="GET", payload=None, headers=None):
    if headers is None:
        headers = {}
    
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            err_detail = json.loads(body)
        except Exception:
            err_detail = body
        return e.code, err_detail
    except Exception as e:
        return 0, str(e)

def run_tests():
    # Random suffix to avoid collisions in DB
    rand = random.randint(1000, 9999)
    username = f"saas_user_{rand}"
    email = f"saas_{rand}@example.com"
    password = f"password_{rand}"
    
    print(f"--- STARTING INTEGRATION TESTS FOR USER: {username} ---")
    
    # 1. Register a new user
    print("\n[Step 1] Registering user...")
    status, res = make_request(
        f"{BASE_URL}/auth/register",
        method="POST",
        payload={"username": username, "email": email, "password": password}
    )
    print("Status:", status)
    print("Response:", res)
    assert status == 200, "Registration failed"
    assert res.get("status") == "success"
    
    # 2. Login to get session token
    print("\n[Step 2] Logging in user...")
    status, login_res = make_request(
        f"{BASE_URL}/auth/login",
        method="POST",
        payload={"username": username, "password": password}
    )
    print("Status:", status)
    print("Response:", login_res)
    assert status == 200, "Login failed"
    user_token = login_res["token"]
    user_id = login_res["user_id"]
    
    # 3. Create an API Key using user session token
    print("\n[Step 3] Creating API key...")
    status, key_res = make_request(
        f"{BASE_URL}/user/keys",
        method="POST",
        payload={"name": "SaaS Test Key"},
        headers={"X-User-Token": user_token}
    )
    print("Status:", status)
    print("Response:", key_res)
    assert status == 200, "API key creation failed"
    api_key = key_res["key"]
    
    # 4. Generate a signal (verifying access is allowed)
    print("\n[Step 4] Requesting signal with valid API Key & User ID...")
    status, signal_res = make_request(
        f"{BASE_URL}/signals/generate",
        method="POST",
        payload={"mode": "Crypto", "pair": "Bitcoin (OTC)", "duration": "15 Seconds"},
        headers={"X-API-Key": api_key, "X-User-Id": str(user_id)}
    )
    print("Status:", status)
    print("Signal:", signal_res.get("signal"), "| Price:", signal_res.get("current_price"))
    assert status == 200, "Signal generation failed with valid API key"
    
    # 5. Access signal without API key/user headers (should fail)
    print("\n[Step 5] Requesting signal without X-API-Key and X-User-Id headers...")
    status, err_res = make_request(
        f"{BASE_URL}/signals/generate",
        method="POST",
        payload={"mode": "Crypto", "pair": "Bitcoin (OTC)", "duration": "15 Seconds"}
    )
    print("Status (Expected 401):", status)
    print("Response:", err_res)
    assert status == 401
    
    # 6. Access signal with mismatched API key & user ID (should fail)
    print("\n[Step 6] Requesting signal with mismatched X-User-Id...")
    status, err_res = make_request(
        f"{BASE_URL}/signals/generate",
        method="POST",
        payload={"mode": "Crypto", "pair": "Bitcoin (OTC)", "duration": "15 Seconds"},
        headers={"X-API-Key": api_key, "X-User-Id": str(user_id + 99)}
    )
    print("Status (Expected 403):", status)
    print("Response:", err_res)
    assert status == 403
    
    # 7. Admin login
    print("\n[Step 7] Logging in as Admin...")
    status, admin_res = make_request(
        f"{BASE_URL}/admin/login",
        method="POST",
        payload={"password": "07862433"}
    )
    print("Status:", status)
    print("Response:", admin_res)
    assert status == 200, "Admin login failed"
    admin_token = admin_res["token"]
    
    # 8. Admin lists users
    print("\n[Step 8] Admin listing users...")
    status, users_res = make_request(
        f"{BASE_URL}/admin/users",
        method="GET",
        headers={"X-Admin-Token": admin_token}
    )
    print("Status:", status)
    print("First few users in system:")
    for u in users_res[:3]:
        print(f" - ID: {u['id']}, Username: {u['username']}, Active: {u['is_active']}")
    assert status == 200
    
    # 9. Admin suspends the user
    print(f"\n[Step 9] Admin suspending user {user_id}...")
    status, susp_res = make_request(
        f"{BASE_URL}/admin/users/{user_id}/status",
        method="PATCH",
        payload={"is_active": False},
        headers={"X-Admin-Token": admin_token}
    )
    print("Status:", status)
    print("Response:", susp_res)
    assert status == 200
    
    # 10. Verify signal generation fails due to user suspended
    print("\n[Step 10] Requesting signal when user is suspended...")
    status, susp_signal_res = make_request(
        f"{BASE_URL}/signals/generate",
        method="POST",
        payload={"mode": "Crypto", "pair": "Bitcoin (OTC)", "duration": "15 Seconds"},
        headers={"X-API-Key": api_key, "X-User-Id": str(user_id)}
    )
    print("Status (Expected 403):", status)
    print("Response:", susp_signal_res)
    assert status == 403
    assert "suspended" in str(susp_signal_res.get("detail")).lower()
    
    # 11. Admin reactivates user
    print(f"\n[Step 11] Admin reactivating user {user_id}...")
    status, react_res = make_request(
        f"{BASE_URL}/admin/users/{user_id}/status",
        method="PATCH",
        payload={"is_active": True},
        headers={"X-Admin-Token": admin_token}
    )
    print("Status:", status)
    print("Response:", react_res)
    assert status == 200
    
    # 12. Admin disables the API key
    print(f"\n[Step 12] Admin disabling API Key: {api_key}...")
    status, dis_res = make_request(
        f"{BASE_URL}/admin/keys/{api_key}/status",
        method="PATCH",
        payload={"is_active": False},
        headers={"X-Admin-Token": admin_token}
    )
    print("Status:", status)
    print("Response:", dis_res)
    assert status == 200
    
    # 13. Verify signal generation fails due to API Key disabled
    print("\n[Step 13] Requesting signal when API key is disabled...")
    status, dis_signal_res = make_request(
        f"{BASE_URL}/signals/generate",
        method="POST",
        payload={"mode": "Crypto", "pair": "Bitcoin (OTC)", "duration": "15 Seconds"},
        headers={"X-API-Key": api_key, "X-User-Id": str(user_id)}
    )
    print("Status (Expected 403):", status)
    print("Response:", dis_signal_res)
    assert status == 403
    assert "disabled" in str(dis_signal_res.get("detail")).lower()
    
    # 14. User deletes API key
    print(f"\n[Step 14] User revoking API key: {api_key}...")
    status, del_res = make_request(
        f"{BASE_URL}/user/keys/{api_key}",
        method="DELETE",
        headers={"X-User-Token": user_token}
    )
    print("Status:", status)
    print("Response:", del_res)
    assert status == 200
    
    # 15. Verify signal generation fails due to API Key missing
    print("\n[Step 15] Requesting signal after API key was deleted...")
    status, miss_signal_res = make_request(
        f"{BASE_URL}/signals/generate",
        method="POST",
        payload={"mode": "Crypto", "pair": "Bitcoin (OTC)", "duration": "15 Seconds"},
        headers={"X-API-Key": api_key, "X-User-Id": str(user_id)}
    )
    print("Status (Expected 403):", status)
    print("Response:", miss_signal_res)
    assert status == 403
    assert "not found" in str(miss_signal_res.get("detail")).lower()

    # 16. Multi-Tenant Scoping Verification
    print("\n[Step 16] Multi-Tenant Scoping Verification (User A vs User B)...")
    
    # Register & Setup User A
    rand_a = random.randint(10000, 99999)
    user_a_name = f"tenant_a_{rand_a}"
    make_request(
        f"{BASE_URL}/auth/register", method="POST",
        payload={"username": user_a_name, "email": f"{user_a_name}@example.com", "password": "passwordA"}
    )
    _, login_a = make_request(
        f"{BASE_URL}/auth/login", method="POST",
        payload={"username": user_a_name, "password": "passwordA"}
    )
    token_a = login_a["token"]
    id_a = login_a["user_id"]
    _, key_a_res = make_request(
        f"{BASE_URL}/user/keys", method="POST",
        payload={"name": "Key A"}, headers={"X-User-Token": token_a}
    )
    key_a = key_a_res["key"]

    # Register & Setup User B
    rand_b = random.randint(10000, 99999)
    user_b_name = f"tenant_b_{rand_b}"
    make_request(
        f"{BASE_URL}/auth/register", method="POST",
        payload={"username": user_b_name, "email": f"{user_b_name}@example.com", "password": "passwordB"}
    )
    _, login_b = make_request(
        f"{BASE_URL}/auth/login", method="POST",
        payload={"username": user_b_name, "password": "passwordB"}
    )
    token_b = login_b["token"]
    id_b = login_b["user_id"]
    _, key_b_res = make_request(
        f"{BASE_URL}/user/keys", method="POST",
        payload={"name": "Key B"}, headers={"X-User-Token": token_b}
    )
    key_b = key_b_res["key"]

    # User A generates a signal
    print("User A generating signal...")
    status_sig_a, sig_a_res = make_request(
        f"{BASE_URL}/signals/generate", method="POST",
        payload={"mode": "Crypto", "pair": "Bitcoin (OTC)", "duration": "15 Seconds"},
        headers={"X-API-Key": key_a, "X-User-Id": str(id_a)}
    )
    assert status_sig_a == 200
    saved_a = sig_a_res.get("signal") != "WAIT"

    # User A adds Bitcoin (OTC) to watchlist
    print("User A adding to watchlist...")
    status_w_a, _ = make_request(
        f"{BASE_URL}/watchlist", method="POST",
        payload={"mode": "Crypto", "pair": "Bitcoin (OTC)", "duration": "15 Seconds"},
        headers={"X-API-Key": key_a, "X-User-Id": str(id_a)}
    )
    assert status_w_a == 200

    # User B checks watchlist & history (should be empty)
    print("User B checking watchlist...")
    _, wl_b = make_request(
        f"{BASE_URL}/watchlist", method="GET",
        headers={"X-API-Key": key_b, "X-User-Id": str(id_b)}
    )
    assert len(wl_b) == 0, f"User B watchlist should be empty, got {wl_b}"

    print("User B checking history...")
    _, hist_b = make_request(
        f"{BASE_URL}/history", method="GET",
        headers={"X-API-Key": key_b, "X-User-Id": str(id_b)}
    )
    assert len(hist_b) == 0, f"User B history should be empty, got {hist_b}"

    # User B adds Ethereum (OTC) to watchlist & generates a signal
    print("User B adding to watchlist...")
    make_request(
        f"{BASE_URL}/watchlist", method="POST",
        payload={"mode": "Crypto", "pair": "Ethereum (OTC)", "duration": "15 Seconds"},
        headers={"X-API-Key": key_b, "X-User-Id": str(id_b)}
    )
    print("User B generating signal...")
    status_sig_b, sig_b_res = make_request(
        f"{BASE_URL}/signals/generate", method="POST",
        payload={"mode": "Crypto", "pair": "Ethereum (OTC)", "duration": "15 Seconds"},
        headers={"X-API-Key": key_b, "X-User-Id": str(id_b)}
    )
    assert status_sig_b == 200
    saved_b = sig_b_res.get("signal") != "WAIT"

    # Re-verify User A's isolation
    _, wl_a = make_request(
        f"{BASE_URL}/watchlist", method="GET",
        headers={"X-API-Key": key_a, "X-User-Id": str(id_a)}
    )
    assert len(wl_a) == 1 and wl_a[0]["pair"] == "Bitcoin (OTC)", f"User A watchlist incorrect: {wl_a}"

    _, hist_a = make_request(
        f"{BASE_URL}/history", method="GET",
        headers={"X-API-Key": key_a, "X-User-Id": str(id_a)}
    )
    expected_count_a = 1 if saved_a else 0
    assert len(hist_a) == expected_count_a, f"User A history count incorrect: expected {expected_count_a}, got {len(hist_a)}"
    if saved_a:
        assert hist_a[0].get("pair") == "Bitcoin (OTC)"

    # Re-verify User B's isolation
    _, wl_b_final = make_request(
        f"{BASE_URL}/watchlist", method="GET",
        headers={"X-API-Key": key_b, "X-User-Id": str(id_b)}
    )
    assert len(wl_b_final) == 1 and wl_b_final[0]["pair"] == "Ethereum (OTC)", f"User B final watchlist incorrect: {wl_b_final}"

    _, hist_b_final = make_request(
        f"{BASE_URL}/history", method="GET",
        headers={"X-API-Key": key_b, "X-User-Id": str(id_b)}
    )
    expected_count_b = 1 if saved_b else 0
    assert len(hist_b_final) == expected_count_b, f"User B history count incorrect: expected {expected_count_b}, got {len(hist_b_final)}"
    if saved_b:
        assert hist_b_final[0].get("pair") == "Ethereum (OTC)"

    print("Multi-tenant isolation verified successfully!")
    
    print("\n--- ALL INTEGRATION TESTS PASSED SUCCESSFULLY! ---")

if __name__ == "__main__":
    run_tests()
