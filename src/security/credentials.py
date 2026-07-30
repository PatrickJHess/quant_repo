import os
import sys
import getpass


def secure_key_setup(key_name="FRED_KEY"):
    """
    The master UI for setting up API keys. Handles Colab, Local Jupyter,
    and Ephemeral (Binder) environments automatically, with live validation.
    """
    try:
        from IPython.display import clear_output, display, HTML
    except ImportError:
        clear_output = lambda: None
        display = lambda x: print(x)
        HTML = lambda x: x

    # --- INTERNAL VALIDATION HELPER ---
    def _validate_key(name, value):
        import requests
        name_upper = name.upper()

        if "FRED" in name_upper:
            print(f"🔒 Authenticating {name} with FRED servers...")
            if len(value) != 32: return False
            try:
                url = f"https://api.stlouisfed.org/fred/series?series_id=GDP&api_key={value}&file_type=json"
                return requests.get(url).status_code == 200
            except Exception: return False

        elif "ALPHA" in name_upper:
            print(f"🔒 Authenticating {name} with AlphaVantage...")
            try:
                url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=IBM&apikey={value}"
                resp = requests.get(url).json()
                return "Error Message" not in resp
            except Exception: return False

        elif "MASSIVE" in name_upper:
            print(f"🔒 Authenticating {name} with Massive reference servers...")
            try:
                url = f"https://api.massive.com/v3/reference/tickers?limit=1&apiKey={value}"
                return requests.get(url).status_code == 200
            except Exception: return False

        else:
            # The graceful bypass for custom keys
            print(f"ℹ️ Note: '{name}' is not recognized as FRED, ALPHA, or MASSIVE.")
            print(f"   Skipping live network validation. Key loaded directly.")
            return True

    # 1. Detect Environment
    import sys, os, getpass
    in_colab = 'google.colab' in sys.modules
    in_binder = 'BINDER_URL' in os.environ or 'BINDER_PORT' in os.environ

    class StopExecution(Exception):
        def _render_traceback_(self):
            pass

    if in_colab:
        from google.colab import userdata
        from google.colab import output

        status_msg = "" # Used to display errors if they click the button too early

        while True:
            try:
                # STATE 1: Vault Check
                colab_key = userdata.get(key_name)
                if colab_key:
                    clear_output()
                    if _validate_key(key_name, colab_key):
                        os.environ[key_name] = colab_key
                        clear_output()
                        display(HTML(f"""
                        <div style="background-color: #d4edda; padding: 15px; border-radius: 8px; border-left: 6px solid #28a745; max-width: 600px; font-family: sans-serif;">
                            <h4 style="margin-top: 0; color: #155724; margin-bottom: 5px;">&#10004;&#65039; Key Authenticated & Active!</h4>
                            <p style="margin-top: 0; color: #155724; margin-bottom: 0;">We verified <b>{key_name}</b> from your Secrets and securely loaded it. You are ready to fetch data!</p>
                        </div>
                        """))
                        return
                    else:
                        status_msg = f"""
                        <div style="background-color: #f8d7da; padding: 15px; border-radius: 8px; border-left: 6px solid #dc3545; max-width: 600px; font-family: sans-serif; margin-bottom: 15px;">
                            <h4 style="margin-top: 0; color: #721c24; margin-bottom: 5px;">&#10060; Invalid Key Detected</h4>
                            <p style="margin-top: 0; color: #721c24; margin-bottom: 0;">We found <b>{key_name}</b>, but authentication failed. Please fix any typos in the sidebar.</p>
                        </div>
                        """
            except Exception as e:
                # STATE 2: Locked (NotebookAccessError)
                if "Access" in str(type(e).__name__):
                    status_msg = f"""
                    <div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; border-left: 6px solid #ffc107; max-width: 600px; font-family: sans-serif; margin-bottom: 15px;">
                        <h4 style="margin-top: 0; color: #856404; margin-bottom: 5px;">&#128273; Activation Required</h4>
                        <p style="margin-top: 0; color: #856404; margin-bottom: 0;">We found <b>{key_name}</b>, but you forgot to toggle <b>"Notebook access"</b> to ON. Please toggle it and try again.</p>
                    </div>
                    """
                else:
                    pass # Doesn't exist yet, which is perfectly normal.

            # --- STATE 3: THE SEAMLESS SETUP WIZARD ---
            clear_output()
            if status_msg:
                display(HTML(status_msg))
                status_msg = "" # Clear it so it doesn't loop forever

            display(HTML(f"""
            <div style="font-family: sans-serif; max-width: 600px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; margin-bottom: 15px;">
                <div style="background-color: #f8f9fa; padding: 15px; border-bottom: 1px solid #ddd;">
                    <h3 style="margin: 0; color: #1a73e8;">&#128274; {key_name} Setup Required</h3>
                </div>
                <div style="padding: 20px;">
                    <p style="margin-top: 0; margin-bottom: 15px;">Follow these fast steps to securely store your API key:</p>
                    <ol style="margin-top: 0; padding-left: 20px; line-height: 1.8; color: #333;">
                        <li>Click the <b>Key Icon</b> (&#128273;) on the left sidebar.</li>
                        <li>Click <b>"Add new secret"</b>.</li>
                        <li>Paste your actual API Key into the <b>"Value"</b> box first (since it's on your clipboard!).</li>
                        <li>Copy this exact name: <button onclick="navigator.clipboard.writeText('{key_name}'); this.innerHTML='&#9989; Copied!'; setTimeout(() => this.innerHTML='&#128203; {key_name}', 2000);" style="margin-left: 8px; padding: 4px 8px; background: #e8f0fe; color: #1a73e8; border: 1px solid #1a73e8; border-radius: 4px; cursor: pointer; font-family: monospace; font-weight: bold;">&#128203; {key_name}</button><br>and paste it into the <b>"Name"</b> box.</li>
                        <li>Toggle <b>"Notebook access"</b> to <span style="color: #1a73e8; font-weight: bold;">ON (Blue)</span>.</li>
                    </ol>
                    
                    <div style="display: flex; gap: 10px; margin-top: 15px;">
                        <button id="check-btn-{key_name}" style="flex: 2; padding: 12px; background: #34a853; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold; transition: 0.2s;">
                            &#10004;&#65039; Authenticate Now
                        </button>
                        <button id="stop-btn-{key_name}" style="flex: 1; padding: 12px; background: #dc3545; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold; transition: 0.2s;">
                            &#10060; Stop
                        </button>
                    </div>
                </div>
            </div>

<script>
              // The Promise now listens to BOTH buttons and returns a command string
              window.promise_{key_name} = new Promise(function(resolve) {{
                
                document.getElementById('check-btn-{key_name}').onclick = function() {{
                  this.innerHTML = "&#8987; Authenticating...";
                  this.style.backgroundColor = "#2d9249";
                  this.style.pointerEvents = "none";
                  document.getElementById('stop-btn-{key_name}').style.pointerEvents = "none";
                  resolve("check"); // Signal Python to loop and check again
                }};
                
                document.getElementById('stop-btn-{key_name}').onclick = function() {{
                  this.innerHTML = "Stopping...";
                  this.style.backgroundColor = "#c82333";
                  this.style.pointerEvents = "none";
                  document.getElementById('check-btn-{key_name}').style.pointerEvents = "none";
                  resolve("stop"); // Signal Python to halt execution
                }};
                
              }});
            </script>
            """))
            
            # --- THE PAUSE TRAP ---
            try:
                # Python sleeps here waiting for the JS string response
                action = output.eval_js(f"window.promise_{key_name}")
                
                # If the user clicked Stop, break the script entirely
                if action == "stop":
                    clear_output()
                    print("\n\u26A0\uFE0F Setup cancelled by user.")
                    raise StopExecution
                    
            except KeyboardInterrupt:
                clear_output()
                print("\n\u26A0\uFE0F Setup cancelled by user (KeyboardInterrupt).")
                raise StopExecution
else:
        # --- JUPYTER / BINDER LOGIC ---
        filename = f".{key_name.lower()}"
        
        # Search for an existing file locally and in the Home directory
        current_dir = os.path.abspath(os.getcwd())
        found_file_path = None
        
        # Check Local Tree First
        while True:
            potential_path = os.path.join(current_dir, filename)
            if os.path.exists(potential_path):
                found_file_path = potential_path
                break 
            parent_dir = os.path.dirname(current_dir)
            if current_dir == parent_dir:
                break 
            current_dir = parent_dir
            
        # Check Home Directory if not found locally
        home_dir_path = os.path.join(os.path.expanduser("~"), filename)
        if not found_file_path and os.path.exists(home_dir_path):
            found_file_path = home_dir_path

        # 4. Set the final target_file path
        if found_file_path:
            target_file = found_file_path # Overwrite existing
        else:
            # DEFAULT TO GLOBAL HOME DIRECTORY FOR NEW KEYS
            target_file = home_dir_path 

        # UI: Warning if existing file found (Local only)
        if not in_binder and os.path.exists(target_file):
            # ... (Keep your existing overwrite warning logic here) ...
        # UI: Warning if existing file found (Local only)
        if not in_binder and os.path.exists(target_file):
            display(HTML(f"""<div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; border-left: 6px solid #ffc107; font-family: sans-serif; max-width: 600px; margin-bottom: 10px;"><h4 style="margin-top: 0; color: #856404; margin-bottom: 5px;">&#9888;&#65039; WARNING: Key Already Exists</h4><p style="margin-top: 5px; color: #856404; margin-bottom: 0;">A saved key was already found in your vault.</p></div>"""))
            try:
                confirm = input("Do you want to OVERWRITE it? [y/N]: ")
                if confirm.strip().lower() not in ['yes', 'y']:
                    with open(target_file, "r") as f:
                        os.environ[key_name] = f.read().strip()
                    clear_output()
                    display(HTML("""<div style="margin-top: 10px; color: #155724; font-weight: bold; background: #d4edda; padding: 15px; border-radius: 8px; border-left: 6px solid #28a745; max-width: 600px;">&#10005; Setup cancelled. Your existing key was retained <b>and loaded into the environment!</b></div>"""))
                    return
            except KeyboardInterrupt:
                with open(target_file, "r") as f:
                    os.environ[key_name] = f.read().strip()
                clear_output()
                display(HTML("""<div style="margin-top: 10px; color: #155724; font-weight: bold; background: #d4edda; padding: 15px; border-radius: 8px; border-left: 6px solid #28a745; max-width: 600px;">&#10005; Interrupted. Your existing key was retained <b>and loaded into the environment!</b></div>"""))
                return
            clear_output()

        # UI: The Request Box
        if in_binder:
             display(HTML(f"""<div style="background-color: #e2e3e5; padding: 15px; border-radius: 8px; border-left: 6px solid #6c757d; font-family: sans-serif; max-width: 600px; margin-bottom: 10px;"><h3 style="margin-top: 0; color: #383d41; margin-bottom: 5px;">&#9201;&#65039; Ephemeral Session Setup</h3><p style="margin-top: 0; margin-bottom: 0;">You are running in a temporary session. Please paste your <b>{key_name}</b> below.<br><br><b>Note:</b> This key will only persist as long as this browser session remains active.</p></div>"""))
        else:
             display(HTML(f"""<div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 6px solid #4285f4; font-family: sans-serif; max-width: 600px; margin-bottom: 10px;"><h3 style="margin-top: 0; color: #1a73e8; margin-bottom: 5px;">&#128274; Secure Key Setup</h3><p style="margin-top: 0; margin-bottom: 0;">Please paste your <b>{key_name}</b> below. It will be safely vaulted as a hidden file.</p></div>"""))

        # The Input Loop
        print(f"Enter your {key_name} (or type 'quit' to cancel):")
        while True:
            try:
                key_input = getpass.getpass(prompt="> ").strip()
                if key_input.lower() in ['q', 'quit', 'cancel', 'exit']:
                    clear_output()
                    print("\n\u26A0\uFE0F Setup cancelled by user. No key was saved.")
                    return

                if key_input:
                    # VALIDATION INTERCEPT
                    if _validate_key(key_name, key_input):
                        clear_output()
                        break
                    else:
                        clear_output()
                        print(f"\u274C Invalid {key_name} detected! Authentication failed.")
                        print(f"Please check for typos and try again (or type 'quit' to cancel):")
                else:
                    clear_output()
                    print("\u26A0\uFE0F Input cannot be empty. Please paste your key (or type 'quit' to cancel):")
            except KeyboardInterrupt:
                clear_output()
                print("\n\u26A0\uFE0F Cell execution interrupted. Setup cancelled.")
                return

        # INJECT INTO ENVIRONMENT IMMEDIATELY
        os.environ[key_name] = key_input

        # Save Logic (Skip saving to disk if Binder)
        if in_binder:
            display(HTML(f"""<div style="margin-top: 10px; color: #137333; font-weight: bold; background: #e6f4ea; padding: 15px; border-radius: 8px; border-left: 6px solid #34a853; max-width: 600px;">&#127881; <b>Success! Key authenticated and loaded to environment.</b><br><span style="color: #0d652d; font-size: 0.9em;">(Remember: It will be cleared when this session ends.)</span></div>"""))
        else:
            try:
                with open(target_file, "w") as f: f.write(key_input)
                try: os.chmod(target_file, 0o600)
                except: pass
                display(HTML(f"""<div style="margin-top: 10px; color: #137333; font-weight: bold; background: #e6f4ea; padding: 15px; border-radius: 8px; border-left: 6px solid #34a853; max-width: 600px;">&#127881; <b>Success! Your key has been verified and safely vaulted in <code>{target_file}</code></b><br><span style="color: #0d652d; font-size: 0.9em;">&#128161; <b>Pro Tip:</b> Future notebooks will automatically load it!</span></div>"""))
            except Exception as e:
                clear_output()
                print(f"\n\u274C Error saving key: {e}")


def load_key_to_env(key_name="FRED_KEY"):
    """
    Silently loads the API key. If it fails, acts as a router to the Setup UI.
    """
    import os, sys
    if os.environ.get(key_name): return

    in_colab = 'google.colab' in sys.modules
    if in_colab:
        try:
            from google.colab import userdata
            colab_key = userdata.get(key_name)
            if colab_key:
                os.environ[key_name] = colab_key
                return
        except: pass 

    filename = f".{key_name.lower()}"
    
    # 1. Search up the directory tree
    current_dir = os.path.abspath(os.getcwd())
    found_key = None
    
    while True:
        potential_path = os.path.join(current_dir, filename)
        if os.path.exists(potential_path):
            found_key = potential_path
            break
            
        parent_dir = os.path.dirname(current_dir)
        if current_dir == parent_dir:
            break
        current_dir = parent_dir
        
    # 2. Fallback to the User's Home Directory (~/)
    if not found_key:
        home_path = os.path.join(os.path.expanduser("~"), filename)
        if os.path.exists(home_path):
            found_key = home_path

    # 3. Load if found
    if found_key:
        with open(found_key, "r") as f:
            saved_key = f.read().strip()
            if saved_key:
                os.environ[key_name] = saved_key
                return

    # IF ALL FAILS -> Route to Setup UI
    secure_key_setup(key_name)
    
    # The Colab Trap
    if in_colab:
        raise RuntimeError(f"[\u26A0\uFE0F] Setup required! Please complete the wizard above, then re-run this cell.")


def get_api_key(api_key: str = None, key_name: str = "API_KEY", fallback_names: list = None) -> str:
    """
    Universally hunts for an API key across Colab, Local OS, and manual inputs.
    Returns the key as a string, or None if the user leaves the prompt blank.
    """
    if api_key:
        return api_key
        
    if not fallback_names:
        fallback_names = [key_name, key_name.upper(), key_name.lower()]

    # 1. CHECK COLAB SECRETS (Safe Check)
    if 'google.colab' in sys.modules:
        try:
            from google.colab import userdata
            active_secrets = userdata.get_keys() if hasattr(userdata, 'get_keys') else []
            
            for name in fallback_names:
                if name in active_secrets:
                    potential_key = userdata.get(name)
                    if potential_key:
                        print(f"✅ Key loaded seamlessly from Colab Secrets ('{name}')")
                        return potential_key
        except ImportError:
            pass 

    # 2. CHECK OS ENVIRONMENT
    for name in fallback_names:
        if os.environ.get(name):
            print(f"✅ Key loaded from local environment ('{name}')")
            return os.environ.get(name)

    # 3. FALLBACK PROMPT
    print(f"⚠️ Could not find '{key_name}' in Colab Secrets or local environment.")
    print("If you have a key, paste it now; otherwise just press Enter:")
    key_input = getpass.getpass(prompt="> ").strip()
    
    if key_input:
        os.environ[key_name] = key_input 
        print("✅ Key loaded successfully from manual input!")
        return key_input
        
    # If they press enter without typing anything
    return None
