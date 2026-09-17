import os
import sys
import urllib.request
import re
import subprocess
import importlib
import importlib.metadata

def check_dependencies():
    """
    Checks if core dependencies from pyproject.toml are installed locally.
    Prompts for local auto-installation, but silently auto-installs in 
    cloud environments (Binder/Colab/JupyterHub).
    """
    required_packages = [
        "numpy", "pandas", "requests", "openpyxl", "pathvalidate", 
        "python-dateutil", "pandas-datareader", "pandas_market_calendars", 
        "pyarrow", "matplotlib", "altair", "holidays", "html5lib", 
        "scipy", "statsmodels", "massive"
    ]
    
    pip_only_packages = {"massive"}
    
    missing_packages = []
    for pkg in required_packages:
        try:
            importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            missing_packages.append(pkg)

    if not missing_packages:
        return True

    print(f"⚠️ Missing dependencies detected: {', '.join(missing_packages)}")
    
    # Robust Cloud detection logic
    is_colab = 'google.colab' in sys.modules
    is_cloud = is_colab or any(key in os.environ for key in [
        'BINDER_URL', 
        'BINDER_REPO_URL', 
        'BINDER_PORT', 
        'JUPYTERHUB_USER'
    ])
    
    if is_cloud:
        print("☁️ Cloud environment detected. Bypassing prompt and auto-installing...")
        user_choice = 'y'
    else:
        # Pause and wait for user confirmation locally
        try:
            user_choice = input("Would you like to automatically install these missing dependencies? (y/n): ").strip().lower()
        except EOFError:
            # Handles headless environments where input() fails
            user_choice = 'n'

    is_conda = os.path.exists(os.path.join(sys.prefix, 'conda-meta'))
    
    conda_pkgs = [pkg for pkg in missing_packages if pkg not in pip_only_packages]
    pip_pkgs = [pkg for pkg in missing_packages if pkg in pip_only_packages]

    # Fallback to manual installation if the user aborts
    if user_choice != 'y':
        print("\n❌ Auto-installation aborted by user.")
        print("-" * 50)
        
        if is_conda:
            print("Since you are using Conda, please run these commands in a new notebook cell:")
            if conda_pkgs:
                print(f"    !conda install -y -c conda-forge {' '.join(conda_pkgs)}")
            if pip_pkgs:
                print(f"    !pip install {' '.join(pip_pkgs)}")
        else:
            print("Please run this command in a new notebook cell:")
            print(f"    !pip install {' '.join(missing_packages)}")
            
        print("-" * 50)
        return False

    # Proceed with auto-installation
    print("\n🔄 Auto-installing missing packages (this may take a moment)...")
    
    if is_conda:
        if conda_pkgs:
            print(f"📦 Installing via Conda: {', '.join(conda_pkgs)}")
            try:
                subprocess.check_call(
                    ["conda", "install", "-y", "-q", "-c", "conda-forge"] + conda_pkgs,
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL
                )
            except subprocess.CalledProcessError:
                print("⚠️ Conda install failed. Falling back to pip for remaining packages...")
                pip_pkgs.extend(conda_pkgs) 
                
        if pip_pkgs:
            print(f"📦 Installing via pip: {', '.join(pip_pkgs)}")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q"] + pip_pkgs,
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            
    else:
        print(f"📦 Installing via pip: {', '.join(missing_packages)}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q"] + missing_packages,
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
    print("✅ All dependencies installed successfully.")
    print("-" * 50)
    return True

    # Proceed with auto-installation
    print("\n🔄 Auto-installing missing packages (this may take a moment)...")
    
    if is_conda:
        if conda_pkgs:
            print(f"📦 Installing via Conda: {', '.join(conda_pkgs)}")
            try:
                subprocess.check_call(
                    ["conda", "install", "-y", "-q", "-c", "conda-forge"] + conda_pkgs,
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL
                )
            except subprocess.CalledProcessError:
                print("⚠️ Conda install failed. Falling back to pip for remaining packages...")
                pip_pkgs.extend(conda_pkgs) 
                
        if pip_pkgs:
            print(f"📦 Installing via pip: {', '.join(pip_pkgs)}")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q"] + pip_pkgs,
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            
    else:
        print(f"📦 Installing via pip: {', '.join(missing_packages)}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q"] + missing_packages,
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
    print("✅ All dependencies installed successfully.")
    print("-" * 50)
    return True

def import_financial_quant():
    """
    Auto-installer and updater for the financial_quant package.
    Context-aware: Skips version checks in cloud environments, 
    but prevents redundant installs if already in hot memory.
    Safely purges all submodules during a local update to prevent stale memory.
    """
    repo_install_url = "git+https://github.com/PatrickJHess/quant_repo.git"
    github_url = "https://raw.githubusercontent.com/PatrickJHess/quant_repo/master/src/financial_quant/__init__.py"
    
    # =========================================================
    # 1. Environment Detection & Cloud Logic
    # =========================================================
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
            # Note: No --no-deps here! We WANT the cloud to auto-install dependencies.
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", repo_install_url])
            print("✅ Installation complete!")
            import financial_quant as fq
            return fq  # STOP HERE for cloud users

    # =========================================================
    # 2. Local Environment Logic 
    # =========================================================
    
    # 0. Check dependencies before touching the local environment!
    if not check_dependencies():
        print("❌ Installation aborted due to missing dependencies.")
        return None

    # 1. Check local version
    try:
        import financial_quant
        local_version = getattr(financial_quant, "__version__", "Unknown")
    except ImportError:
        local_version = "Not Installed"
    except Exception as e:
        print(f"⚠️ Local installation is broken ({type(e).__name__}).")
        local_version = "Broken"

    # 2. Fetch remote version ONLY if local is intact
    remote_version = "Unknown"
    if local_version not in ["Not Installed", "Broken"]:
        try:
            req = urllib.request.Request(github_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                remote_code = response.read().decode('utf-8')
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', remote_code)
            remote_version = match.group(1) if match else "Unknown"
        except Exception as e:
            print(f"⚠️ Could not connect to GitHub to check for updates: {e}")

    # 3. Decision Tree: Install, Fix, Update, or Skip
    if local_version == "Not Installed":
        print("📦 'financial_quant' not found locally. Installing from GitHub...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--no-deps", repo_install_url])
        print("✅ Installation complete!")
        
    elif local_version == "Broken" or (local_version != remote_version and remote_version != "Unknown"):
        if local_version == "Broken":
            print("🛠️ Corrupted installation detected. Forcing a fresh reinstall...")
        else:
            print(f"⚠️ Update found! (Local: {local_version} ➡️ Latest: {remote_version})")
            print("🔄 Automatically updating financial_quant. Please wait...")
            
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-q", "--upgrade", 
            "--force-reinstall", "--no-deps", "--no-cache-dir", repo_install_url
        ])
        print("✅ Process complete!")
        
        # Recursive Memory Wipe
        modules_to_delete = [
            name for name in sys.modules 
            if name == "financial_quant" or name.startswith("financial_quant.")
        ]
        for name in modules_to_delete:
            del sys.modules[name]
            
        importlib.invalidate_caches()
        
        print("😕 Note: If newly updated charts or models don't look right, please Restart the Kernel.")
        print("*(Go to `Kernel` ➡️ `Restart Kernel and Run up to Selected Cell...`)*")
        
    else:
        print(f"✅ 'financial_quant' is up to date (Version {local_version}).")

    import financial_quant as fq
    return fq
