import sys
import os
import time
import random
from pathlib import Path

# Add desktop to path so main.py can import relative modules
desktop_path = Path(r"c:\Users\PMLS\Documents\Trading-Bot\desktop")
sys.path.append(str(desktop_path))

from PyQt6.QtWidgets import QApplication, QDialog
from main import LicenseGateWindow, AdminLicenseDialog, TradingSignalWindow
from license_manager import LicenseManager
from api_client import ApiClient

def generate_screenshots():
    # Initialize application
    app = QApplication.instance() or QApplication(sys.argv)
    
    # Setup cache / clients
    license_manager = LicenseManager()
    client = ApiClient()
    
    # 1. Capture LicenseGateWindow (Auth Portal)
    print("Instantiating LicenseGateWindow...")
    gate = LicenseGateWindow(license_manager, client)
    gate.show()
    app.processEvents()
    
    # Capture each tab
    # Tab 0: Sign In
    gate.tabs.setCurrentIndex(0)
    app.processEvents()
    img_path_signin = r"C:\Users\PMLS\.gemini\antigravity-ide\brain\c4a20b06-2872-4674-a3c2-c15b0c0fea05\license_gate_signin.png"
    gate.grab().save(img_path_signin, "PNG")
    print(f"Saved Sign In tab to {img_path_signin}")
    
    # Tab 1: Sign Up
    gate.tabs.setCurrentIndex(1)
    app.processEvents()
    img_path_signup = r"C:\Users\PMLS\.gemini\antigravity-ide\brain\c4a20b06-2872-4674-a3c2-c15b0c0fea05\license_gate_signup.png"
    gate.grab().save(img_path_signup, "PNG")
    print(f"Saved Sign Up tab to {img_path_signup}")
    
    # Tab 2: Admin Access
    gate.tabs.setCurrentIndex(2)
    app.processEvents()
    img_path_admin = r"C:\Users\PMLS\.gemini\antigravity-ide\brain\c4a20b06-2872-4674-a3c2-c15b0c0fea05\license_gate_admin.png"
    gate.grab().save(img_path_admin, "PNG")
    print(f"Saved Admin Access tab to {img_path_admin}")
    
    # Let's perform registration via GUI to get valid credentials and log in
    rand = random.randint(1000, 9999)
    gui_username = f"gui_user_{rand}"
    gui_email = f"gui_{rand}@example.com"
    gui_password = "password123"
    
    print(f"Simulating registration for user {gui_username} in GUI...")
    gate.tabs.setCurrentIndex(1)
    gate.signup_user.setText(gui_username)
    gate.signup_email.setText(gui_email)
    gate.signup_pass.setText(gui_password)
    app.processEvents()
    
    # Click register
    gate.register()
    app.processEvents()
    
    # Give a tiny time for backend response
    time.sleep(0.5)
    app.processEvents()
    
    print("Registration status label:", gate.signup_status.text())
    
    # Close gate
    gate.close()
    
    # 2. Capture AdminLicenseDialog (Admin Dashboard)
    print("Instantiating AdminLicenseDialog...")
    # Seed admin token using backend API calls directly so admin list works
    client.admin_login("07862433")
    
    admin_dialog = AdminLicenseDialog(license_manager, client)
    admin_dialog.show()
    app.processEvents()
    
    # Tab 0: Manage Users
    admin_dialog.tabs.setCurrentIndex(0)
    app.processEvents()
    img_path_users = r"C:\Users\PMLS\.gemini\antigravity-ide\brain\c4a20b06-2872-4674-a3c2-c15b0c0fea05\admin_panel_users.png"
    admin_dialog.grab().save(img_path_users, "PNG")
    print(f"Saved Manage Users tab to {img_path_users}")
    
    # Tab 1: Manage API Keys
    admin_dialog.tabs.setCurrentIndex(1)
    app.processEvents()
    img_path_keys = r"C:\Users\PMLS\.gemini\antigravity-ide\brain\c4a20b06-2872-4674-a3c2-c15b0c0fea05\admin_panel_keys.png"
    admin_dialog.grab().save(img_path_keys, "PNG")
    print(f"Saved Manage API Keys tab to {img_path_keys}")
    
    # Tab 2: Admin Settings
    admin_dialog.tabs.setCurrentIndex(2)
    app.processEvents()
    img_path_settings = r"C:\Users\PMLS\.gemini\antigravity-ide\brain\c4a20b06-2872-4674-a3c2-c15b0c0fea05\admin_panel_settings.png"
    admin_dialog.grab().save(img_path_settings, "PNG")
    print(f"Saved Admin Settings tab to {img_path_settings}")
    
    admin_dialog.close()
    
    # 3. Capture TradingSignalWindow
    print("Instantiating TradingSignalWindow...")
    window = TradingSignalWindow(license_manager, client)
    window.show()
    app.processEvents()
    
    # Grab main window
    img_path_main = r"C:\Users\PMLS\.gemini\antigravity-ide\brain\c4a20b06-2872-4674-a3c2-c15b0c0fea05\main_window_saas.png"
    window.grab().save(img_path_main, "PNG")
    print(f"Saved TradingSignalWindow to {img_path_main}")
    
    # Simulating a signal generation request from the GUI!
    print("Simulating Signal Generation request for Binance Spot BTC/USDT...")
    window.mode_combo.setCurrentText("Binance Spot")
    window.pair_combo.setCurrentText("BTC/USDT")
    window.duration_combo.setCurrentText("15 Seconds")
    app.processEvents()
    
    # Click generate button
    window.primary_generate_button.click()
    app.processEvents()
    
    print("Waiting for signal worker thread to complete...")
    start = time.time()
    while not window.primary_generate_button.isEnabled() and (time.time() - start) < 5:
        app.processEvents()
        time.sleep(0.1)
        
    app.processEvents()
    
    # Grab main window again with the signal details populated
    img_path_main_sig = r"C:\Users\PMLS\.gemini\antigravity-ide\brain\c4a20b06-2872-4674-a3c2-c15b0c0fea05\main_window_saas_with_signal.png"
    window.grab().save(img_path_main_sig, "PNG")
    print(f"Saved TradingSignalWindow with active signal to {img_path_main_sig}")
    
    window.close()
    print("GUI tests completed!")

if __name__ == "__main__":
    generate_screenshots()
