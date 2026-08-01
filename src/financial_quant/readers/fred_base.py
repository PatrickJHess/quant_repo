import os
import time
import requests
import getpass
from financial_quant.security.credentials import scavenge_api_key
from financial_quant.utils.cache import setup_cache_dir, clear_cache

class FredBase:
    def __init__(self, api_key=None, key_name="fred_key"):
        """
        Base class for FRED. Uses shared utilities for setup, but maintains
        its own reactive network shield.
        """
        # 1. Use shared utility to build cache
        self.cache_dir = setup_cache_dir(folder_name="FRED", shared_env_var="FRED_SHARED_CACHE")

        # 2. Use shared utility to hunt for the key (this auto-triggers the UI wizard if needed!)
        fallback_names = [key_name, "fred_key", "FRED_API_KEY", "FRED_KEY"]
        self.api_key = scavenge_api_key(api_key=api_key, fallback_names=fallback_names)

        # 3. FRED-specific fallback (Graceful degradation)
        if not self.api_key:
            # If we get here, it means the user cancelled the secure_key_setup wizard.
            print("⚠️ No key loaded. Defaulting to pandas_datareader for basic series.")

    # Managing existing cache   
    def clear_cache(self, symbol):
        """
        Clears the cached economic data for a specific FRED series ID.
        Requires an explicit series ID and user confirmation for safety.
        
        Examples:
        - fred_data.clear_cache('GDP')     -> Clears all cached data for Gross Domestic Product
        - fred_data.clear_cache('UNRATE')  -> Clears all cached data for the Unemployment Rate
        """
        cache_clear(self.cache_dir, symbol=symbol)
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
