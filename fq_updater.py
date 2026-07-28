import sys
import subprocess
import urllib.request
import re
import importlib

def import_financial_quant():
    """
    Auto-installer and updater for the financial_quant package.
    Parses pyproject.toml projects via git+https.
    """
    # 1. Raw URL pointing to the src/ directory on master branch
    github_url = "https://raw.githubusercontent.com/PatrickJHess/quant_repo/master/src/financial_quant/__init__.py"
    repo_install_url = "git+https://github.com/PatrickJHess/quant_repo.git"
    
    # 2. Check local version
    try:
        import financial_quant
        local_version = getattr(financial_quant, "__version__", "Unknown")
    except ImportError:
        local_version = "Not Installed"

    # 3. Fetch remote version from GitHub
    try:
        req = urllib.request.Request(github_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            remote_code = response.read().decode('utf-8')
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', remote_code)
        remote_version = match.group(1) if match else "Unknown"
    except Exception as e:
        print(f"⚠️ Could not connect to GitHub to check for updates: {e}")
        remote_version = "Unknown"

    # 4. Decision Tree: Install, Update, or Skip
    if local_version == "Not Installed":
        print("📦 'financial_quant' not found. Installing from GitHub...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", repo_install_url])
        print("✅ Installation complete!")
        
    elif local_version != remote_version and remote_version != "Unknown":
        print(f"⚠️ Update found! (Local: {local_version} ➡️ Latest: {remote_version})")
        print("🔄 Automatically updating financial_quant. Please wait...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-q", "--upgrade", 
            "--force-reinstall", "--no-cache-dir", repo_install_url
        ])
        print("✅ Update complete!")
        
        # Clear out Jupyter's cached import memory
        if "financial_quant" in sys.modules:
            del sys.modules["financial_quant"]
        importlib.invalidate_caches()
        
    else:
        print(f"✅ 'financial_quant' is up to date (Version {local_version}).")

    # 5. Import and return
    import financial_quant as fq
    return fq
