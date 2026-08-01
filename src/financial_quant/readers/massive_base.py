import os
import sys
import time
import json
from massive import RESTClient # Assuming this is what MASSIVE uses
from financial_quant.security.credentials import scavenge_api_key
from financial_quant.utils.cache import setup_cache_dir, cache_clear

class MassiveBase:
    def __init__(self, api_key: str = None, key_name: str = "massive_key", calls_per_minute: int = 4):
        """
        Base class for MASSIVE. Uses shared utilities for setup, but maintains
        its own strict rate limiter and metadata tracker.
        """
        # 1. Use shared utility to build cache
        self.cache_dir = setup_cache_dir(folder_name="MASSIVE_DATA", shared_env_var="MASSIVE_SHARED_CACHE")

        self.history_file = os.path.join(self.cache_dir, "api_history.json")
        self.metadata_file = os.path.join(self.cache_dir, "cache_metadata.json")

        # 2. Use shared utility to hunt for the key
        fallback_names = [key_name, 'MASSIVE', 'massive', 'MASSIVE_KEY', 'massive_key']
        self.api_key = scavenge_api_key(api_key=api_key, fallback_names=fallback_names)

        # 3. MASSIVE-specific fallback (Hard crash)
        if not self.api_key:
             raise ValueError(f"Missing Key! Please run secure_key_setup('{key_name}') in the cell above.")

        self.client = RESTClient(self.api_key)
        self.calls_per_minute = calls_per_minute

    # Managing existing cache 
    def clear_cache(self, symbol):
        """
        Clears the cached market data for a specific contract or ticker.
        Requires an explicit symbol and user confirmation for safety.
        
        Examples:
        - massive_data.clear_cache('ESU6')        -> Clears all timeframes for the ESU6 contract
        - massive_data.clear_cache('ESU6_1_day')  -> Clears ONLY the daily data for ESU6
        """
        cache_clear(self.cache_dir, symbol=symbol)

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
