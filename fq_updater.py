iimport os
import sys
import urllib.request
import re
import subprocess
import importlib

def import_financial_quant():
    """
    Auto-installer and updater for the financial_quant package.
    Context-aware: Skips version checks in cloud environments, 
    but prevents redundant installs if already in hot memory.
    Safely purges all submodules during a local update to prevent stale memory.
    """
    repo_install_url = "git+https://github.com/PatrickJHess/quant_repo.git"
    github_url = "https://raw.githubusercontent.com/PatrickJHess/quant_repo/master/src/financial_quant/__init__.py"
    
    # 1. Environment Detection & Early Stop
    is_colab = 'google.colab' in sys.modules
    is_binder = 'BINDER_PORT' in os.environ

    if is_colab or is_binder:
        # Check hot memory to prevent double-installs in the same session
        try:
            import financial_quant as fq
            print("✅ 'financial_quant' is already loaded in this session.")
            return fq
        except ImportError:
            print("☁️ Cloud environment detected. Installing fresh from GitHub...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", repo_install_url])
            print("✅ Installation complete!")
            import financial_quant as fq
            return fq  # STOP HERE for cloud users

    # =========================================================
    # 2. Local Environment Logic (Only runs if NOT in the cloud)
    # =========================================================
    
    # Check local version
    try:
        import financial_quant
        local_version = getattr(financial_quant, "__version__", "Unknown")
    except ImportError:
        local_version = "Not Installed"

    # Fetch remote version from GitHub
    try:
        req = urllib.request.Request(github_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            remote_code = response.read().decode('utf-8')
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', remote_code)
        remote_version = match.group(1) if match else "Unknown"
    except Exception as e:
        print(f"⚠️ Could not connect to GitHub to check for updates: {e}")
        remote_version = "Unknown"

    # Decision Tree: Install, Update, or Skip
    if local_version == "Not Installed":
        print("📦 'financial_quant' not found locally. Installing from GitHub...")
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
        
        # Recursive Memory Wipe
        modules_to_delete = [
            name for name in sys.modules 
            if name == "financial_quant" or name.startswith("financial_quant.")
        ]
        
        for name in modules_to_delete:
            del sys.modules[name]
            
        importlib.invalidate_caches()
        
        # Dynamic Warning for Local Users
        print("😕 Note: If newly updated charts or models don't look right, please Restart the Kernel.")
        print("*(Go to `Kernel` ➡️ `Restart Kernel and Run up to Selected Cell...`)*")
        
    else:
        print(f"✅ 'financial_quant' is up to date (Version {local_version}).")

    # Import and return for local users 
    import financial_quant as fq
    return fq
