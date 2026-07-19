import os
import sys
from pathlib import Path

# Adjust path to import backend
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import get_settings
from backend.models import SignalResponse, TradingMode, SignalAction, TradeDuration
from datetime import datetime, timezone


def run_test():
    print("Starting Firestore Integration Test...")
    settings = get_settings()
    
    # 1. Temporarily override database type to firestore
    settings.database_type = "firestore"
    
    cred_path = settings.firebase_credentials_path
    if not cred_path.exists():
        print(f"ERROR: firebase-credentials.json not found at: {cred_path}")
        print("Please download your service account key and save it there to run this test.")
        return False
        
    print(f"Found credentials at: {cred_path}")
    
    from backend.database.firestore_repository import FirestoreSignalRepository
    
    try:
        repo = FirestoreSignalRepository()
        print("Successfully initialized Firestore connection!")
        
        # 2. Test Admin Config Seeding
        print("\nTesting Admin Config Seeding...")
        repo.seed_admin_config(default_password="testpassword123")
        hash_val = repo.get_admin_password_hash()
        if hash_val:
            print(f"Success: Admin password hash found: {hash_val}")
        else:
            print("Failed: Admin password hash is empty.")
            return False

        # 3. Test User CRUD
        print("\nTesting User CRUD...")
        test_username = "test_user_999"
        test_email = "test_user_999@test.com"
        
        # Clean up existing if left over from aborted test
        existing = repo.get_user_by_username(test_username)
        if existing:
            print(f"Cleaning up pre-existing user ID: {existing['id']}...")
            repo.db.collection("users").document(str(existing["id"])).delete()
            
        uid = repo.insert_user(test_username, test_email, "dummyhash")
        print(f"Inserted test user with ID: {uid}")
        
        user = repo.get_user_by_id(uid)
        if user and user.get("username") == test_username:
            print(f"Success: Retrieved user by ID: {user['username']}")
        else:
            print("Failed to retrieve user by ID.")
            return False
            
        # 4. Test Watchlist
        print("\nTesting Watchlist...")
        repo.add_watchlist_pair("Crypto", "BTC/USDT", uid)
        watchlist = repo.list_watchlist(uid)
        print(f"Watchlist pairs: {watchlist}")
        if any(w["pair"] == "BTC/USDT" for w in watchlist):
            print("Success: Watchlist item added!")
        else:
            print("Failed: Watchlist item not found.")
            return False
            
        repo.remove_watchlist_pair("Crypto", "BTC/USDT", uid)
        watchlist_empty = repo.list_watchlist(uid)
        if not any(w["pair"] == "BTC/USDT" for w in watchlist_empty):
            print("Success: Watchlist item removed!")
        else:
            print("Failed: Watchlist item still exists.")
            return False

        # 5. Test Signal & Statistics
        print("\nTesting Signal & Statistics...")
        mock_signal = SignalResponse(
            mode=TradingMode.crypto,
            pair="ETH/USDT",
            current_price=2450.50,
            signal=SignalAction.up,
            confidence=85,
            duration=TradeDuration.minute_1,
            market_trend="Strong Bullish",
            status="LIVE",
            analysis=["Test analysis statement"],
            generated_at=datetime.now(timezone.utc)
        )
        sig_id = repo.save_signal(mock_signal, user_id=uid)
        print(f"Saved signal with ID: {sig_id}")
        
        history = repo.list_history(user_id=uid, limit=5)
        print(f"History length retrieved: {len(history)}")
        if len(history) > 0 and history[0].pair == "ETH/USDT":
            print("Success: Retrieved signal history record!")
        else:
            print("Failed to retrieve signal history.")
            return False
            
        # Update Outcome
        repo.update_outcome(sig_id, "WIN", user_id=uid)
        print("Updated signal outcome to WIN")
        
        stats = repo.statistics(user_id=uid)
        print(f"User statistics: {stats}")
        if stats.wins == 1 and stats.tracked_win_rate == 100.0:
            print("Success: Statistics aggregated correctly!")
        else:
            print("Failed: Incorrect statistics mapping.")
            return False

        # 6. Test License
        print("\nTesting License CRUD...")
        test_lic_key = "SS-TEST-KEY-1234"
        # Clean up existing if left over
        repo.delete_license(test_lic_key)
        
        lic_id = repo.insert_license(test_lic_key, "Test Owner", "2030-01-01T00:00:00Z")
        print(f"Inserted license with generated ID: {lic_id}")
        
        lic = repo.get_license_by_key(test_lic_key)
        if lic and lic.get("owner") == "Test Owner":
            print("Success: License verified by key!")
        else:
            print("Failed to retrieve license.")
            return False
            
        repo.activate_license(test_lic_key, "device_pc_999", "test-1.0")
        lic_active = repo.get_license_by_key(test_lic_key)
        if lic_active and lic_active.get("device_id") == "device_pc_999":
            print("Success: License activated for device!")
        else:
            print("Failed: License activation details not stored.")
            return False

        # ── Cleanup ──
        print("\nCleaning up test documents from Firestore...")
        repo.db.collection("users").document(str(uid)).delete()
        repo.db.collection("signal_history").document(str(sig_id)).delete()
        repo.db.collection("licenses").document(test_lic_key).delete()
        print("Cleanup completed successfully!")
        
        print("\n=======================================================")
        print("ALL FIRESTORE INTEGRATION TESTS PASSED SUCCESSFULLY!")
        print("=======================================================")
        return True

    except Exception as e:
        print(f"\nERROR running Firestore tests: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
