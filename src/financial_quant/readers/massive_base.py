import os
import sys
import json
import time
from massive import RESTClient

# NEW: Import the security functions directly from your own package!
from financial_quant.security.credentials import secure_key_setup


class MassiveBase:
    def __init__(self, api_key: str = None, key_name: str = "massive_key", calls_per_minute: int = 4):
        """
        Base class that initializes the cache directories and the API client.
        Relies on `load_key_to_env` to pre-populate os.environ if api_key is not passed.
        """
        # --- CACHE DIRECTORY ROUTING ---
        if 'google.colab' in sys.modules:
            from google.colab import drive
            try:
                drive.mount('/content/drive')
                self.cache_dir = '/content/drive/MyDrive/MASSIVE_DATA'
            except Exception:
                self.cache_dir = os.path.expanduser("~/massive_data")
        else:
            shared_env = os.environ.get("MASSIVE_SHARED_CACHE")
            self.cache_dir = shared_env if shared_env else os.path.expanduser("./massive_data")

        os.makedirs(self.cache_dir, exist_ok=True)
        self.history_file = os.path.join(self.cache_dir, "api_history.json")
        self.metadata_file = os.path.join(self.cache_dir, "cache_metadata.json")

        # --- THE 1-LINE AUTHENTICATION ---
        self.api_key = api_key
        
        # Only query os.environ if key_name actually exists as a string
        if not self.api_key and key_name:
            self.api_key = os.environ.get(key_name)

        if not self.api_key:
            fallback=['MASSIVE','massive','MASSIVE_KEY','massive_key','massive']
            self.api_key=next(filter(None, (os.environ.get(v) for v in fallback)), None)
            if not self.api_key:
              raise ValueError(f"Missing Key! Please run load_key_to_env('{key_name}') in the cell above.")

        self.client = RESTClient(self.api_key)
        self.calls_per_minute = calls_per_minute

    # --- 3. PERSISTENT FREEMIUM TRACKER ---
    def _enforce_speed_limit(self):
        now = time.time()
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    history = json.load(f)
            except Exception:
                history = []
        else:
            history = []

        history = [t for t in history if (now - t) <= 60]

        if len(history) >= self.calls_per_minute:
            wait_time = 60 - (now - history[0]) + 1
            if wait_time > 0:
                print(f"🚦 LIMIT REACHED ({self.calls_per_minute} calls/min).")
                for remaining in range(int(wait_time), 0, -1):
                    sys.stdout.write(f"\r⏳ Cooling down... {remaining}s remaining")
                    sys.stdout.flush()
                    time.sleep(1)
                sys.stdout.write("\r Let's go!                               \n")
                sys.stdout.flush()
                now = time.time()
                history = [t for t in history if (now - t) <= 60]

        history.append(now)
        with open(self.history_file, 'w') as f:
            json.dump(history, f)
        return True

    # --- 4. METADATA VALIDATOR ---
    def _check_cache_metadata(self, cache_id, start_date, end_date):
        """Checks if cached file contains the full required window of dates."""
        if not os.path.exists(self.metadata_file):
            return False
        try:
            with open(self.metadata_file, 'r') as f:
                meta = json.load(f)
        except Exception:
            return False

        if cache_id not in meta:
            return False

        cached_start = meta[cache_id]["start_date"]
        cached_end = meta[cache_id]["end_date"]
        
        # True if requested start/end range sits comfortably inside cached range
        return cached_start <= start_date and cached_end >= end_date

    def _update_cache_metadata(self, cache_id, start_date, end_date):
        meta = {}
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r') as f:
                    meta = json.load(f)
            except Exception:
                pass
        
        meta[cache_id] = {"start_date": start_date, "end_date": end_date}
        with open(self.metadata_file, 'w') as f:
            json.dump(meta, f, indent=2) 

