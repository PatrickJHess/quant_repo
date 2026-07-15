import sys
import os
import requests
import getpass


class FredBase:
    def __init__(self, api_key=None, key_name="fred_key"):
        """
        Base class that initializes the cache directories, authenticates 
        the API key, and provides a resilient network requester.
        """
        # --- CACHE DIRECTORY ROUTING ---
        if 'google.colab' in sys.modules:
            print("☁️ Colab environment detected. Mounting Google Drive...")
            from google.colab import drive
            try:
                drive.mount('/content/drive')
                self.cache_dir = '/content/drive/MyDrive/FRED'
            except Exception as e:
                print(f"✅ Drive mount failed, defaulting to local cache: {e}")
                self.cache_dir = os.path.expanduser("~/fred")
        else:
            # 1. Check for a globally set environment variable for shared Hub environments
            shared_env_path = os.environ.get("FRED_SHARED_CACHE")
            
            if shared_env_path:
                self.cache_dir = shared_env_path
            else:
                # 2. Default lock to the user's personal home directory
                self.cache_dir = os.path.expanduser("~/fred")

        print(f"📂 FRED Cache anchored at: {self.cache_dir}")

        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
            except PermissionError:
                print(f"⚠️ Warning: Lacking permission to create {self.cache_dir}. Cache may fail.")

        # --- API KEY LOGIC ---
        self.api_key = None
        fallback_names = [key_name, "fred_key", "FRED_API_KEY", "FRED_KEY"]

        # 1. EXPLICIT KEY PASSED
        if api_key:
            self.api_key = api_key

        # 2. CHECK COLAB SECRETS
        elif 'google.colab' in sys.modules:
            try:
                from google.colab import userdata
                for name_to_check in fallback_names:
                    try:
                        potential_key = userdata.get(name_to_check)
                        if potential_key:
                            self.api_key = potential_key
                            print(f"✅ Key loaded seamlessly from Colab Secrets ('{name_to_check}')")
                            break 
                    except Exception:
                        continue 
            except ImportError:
                pass 

        # 3. CHECK OS ENVIRONMENT
        if not self.api_key:
            for name_to_check in fallback_names:
                if os.environ.get(name_to_check):
                    self.api_key = os.environ.get(name_to_check)
                    print(f"✅ Key loaded from local environment ('{name_to_check}')")
                    break

        # 4. FALLBACK PROMPT
        if not self.api_key:
            print(f"⚠️ Could not find a key named '{key_name}' in Colab Secrets or local environment.")
            print("If you have a FRED key, paste it now; otherwise just press Enter:")
            key_input = getpass.getpass(prompt="> ")
            if key_input.strip():
                self.api_key = key_input.strip()
                os.environ[key_name] = self.api_key 
                print("✅ Key loaded successfully from manual input!")
            else:
                print("⚠️ No key entered. Defaulting to pandas_datareader.")

    # --- REACTIVE NETWORK SHIELD ---
    def _make_api_request(self, url, max_retries=3, series_id=None):
        """Universal helper to handle API calls, 429 Too Many Requests, and graceful 400 errors."""
        for attempt in range(max_retries):
            try:
                response = requests.get(url)
            except requests.exceptions.RequestException:
                print(f"🌩️ NETWORK ERROR: Failed to reach FRED servers.")
                return None
            
            # 1. Rate Limit Catch (HTTP 429)
            if response.status_code == 429:
                wait_time = 5 * (attempt + 1)
                print(f"🚦 Rate limit hit (HTTP 429)! Sleeping for {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
                continue
                
            # 2. Graceful Bad Request Catch (HTTP 400)
            if response.status_code == 400:
                try:
                    error_msg = response.json().get("error_message", "Unknown FRED API error")
                except ValueError:
                    error_msg = "Invalid request (No JSON message provided by FRED)."
                
                context_str = f" for '{series_id}'" if series_id else ""
                print(f"❌ API REJECTED{context_str}: {error_msg}")
                return None  
                
            # 3. Hard Crash Prevention for other HTTP errors
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(f"🌩️ HTTP ERROR: {e}")
                return None

            # 4. Success! Safely unpack the JSON.
            try:
                return response.json()
            except ValueError:
                print(f"❌ ERROR: FRED returned a successful status, but the data is not valid JSON.")
                return None
            
        print(f"❌ Max retries ({max_retries}) exceeded. The API is strictly rate-limiting you.")
        return None

