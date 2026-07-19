import os
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = ROOT / ".git-portable"
URL = "https://github.com/git-for-windows/git/releases/download/v2.43.0.windows.1/MinGit-2.43.0-64-bit.zip"
ZIP_PATH = ROOT / "mingit.zip"

def main():
    print(f"Downloading MinGit from: {URL}")
    try:
        urllib.request.urlretrieve(URL, ZIP_PATH)
        print("Download complete!")
    except Exception as e:
        print(f"Failed to download MinGit: {e}")
        return

    print(f"Extracting MinGit to: {TARGET_DIR}")
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
            zip_ref.extractall(TARGET_DIR)
        print("Extraction complete!")
    except Exception as e:
        print(f"Failed to extract MinGit: {e}")
        return
    finally:
        if ZIP_PATH.exists():
            ZIP_PATH.unlink()

    git_exe = TARGET_DIR / "cmd" / "git.exe"
    if git_exe.exists():
        print(f"Success! Git portable is available at: {git_exe}")
    else:
        print("Warning: git.exe not found in expected path.")

if __name__ == "__main__":
    main()
