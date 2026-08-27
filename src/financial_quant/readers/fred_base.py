import os
import time
import requests
import getpass
from financial_quant.security.credentials import scavenge_api_key
from financial_quant.utils.cache import setup_cache_dir, cache_clear

class FredBase:

    def __init__(
        self,
        api_key=None,
        key_name="fred_key",
        github_raw_base=None,
        enable_github_repo=False,
    ):
        """Base class for FRED.

        Uses shared utilities for setup, maintains network shields, and configures
        the static GitHub repository fallback tier.
        """
        # 1. Use shared utility to build local cache directory
        self.cache_dir = setup_cache_dir(
            folder_name="FRED", shared_env_var="FRED_SHARED_CACHE"
        )

        # 2. Configure GitHub Static Repo settings
        self.github_raw_base = (
            github_raw_base.rstrip("/") if github_raw_base else None
        )
        self.enable_github_repo = enable_github_repo

        # 3. Use shared utility to hunt for the key
        fallback_names = [key_name, "fred_key", "FRED_API_KEY", "FRED_KEY"]
        self.api_key = scavenge_api_key(
            api_key=api_key, fallback_names=fallback_names
        )

        # 4. FRED-specific fallback (Graceful degradation)
        if not self.api_key:
            print(
                "⚠️ No key loaded. Defaulting to pandas_datareader for basic series."
            )

    # --- CACHE MANAGEMENT ---
    def clear_cache(self, symbol=""):
        """Clears cached Parquet data and metadata JSON files for a FRED series ID.

        Examples:
        - fred_data.clear_cache('GDP')    -> Clears cached Parquet & metadata for GDP
        - fred_data.clear_cache('UNRATE') -> Clears cached Parquet & metadata for UNRATE
        """
        if not symbol:
            print("⚠️ Please provide a series ID (e.g., clear_cache('GDP'))")
            return

        # Target both Parquet and JSON metadata files
        parquet_file = os.path.join(self.cache_dir, f"{symbol}_fred.parquet")
        json_file = os.path.join(self.cache_dir, f"{symbol}_metadata.json")

        removed = False
        for target_file in [parquet_file, json_file]:
            if os.path.exists(target_file):
                try:
                    os.remove(target_file)
                    print(f"🗑️ Deleted: {target_file}")
                    removed = True
                except OSError as e:
                    print(f"⚠️ Error removing {target_file}: {e}")

        if not removed:
            print(f"ℹ️ No cached files found for '{symbol}'.")

        # Call generic utility if available
        if "cache_clear" in globals():
            cache_clear(self.cache_dir, symbol=symbol)

    # --- REACTIVE NETWORK SHIELD ---
    def _make_api_request(self, url, max_retries=3, series_id=None):
        """Universal helper to handle API calls, 429 Rate Limits, and 400 errors."""
        for attempt in range(max_retries):
            try:
                response = requests.get(url)
            except requests.exceptions.RequestException:
                print("🌩️ NETWORK ERROR: Failed to reach FRED servers.")
                return None

            # 1. Rate Limit Catch (HTTP 429)
            if response.status_code == 429:
                wait_time = 5 * (attempt + 1)
                print(
                    f"🚦 Rate limit hit (HTTP 429)! Sleeping for {wait_time}s (Attempt {attempt + 1}/{max_retries})..."
                )
                time.sleep(wait_time)
                continue

            # 2. Graceful Bad Request Catch (HTTP 400)
            if response.status_code == 400:
                try:
                    error_msg = response.json().get(
                        "error_message", "Unknown FRED API error"
                    )
                except ValueError:
                    error_msg = (
                        "Invalid request (No JSON message provided by FRED)."
                    )

                context_str = f" for '{series_id}'" if series_id else ""
                print(f"❌ API REJECTED{context_str}: {error_msg}")
                return None

            # 3. Hard Crash Prevention for other HTTP errors
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(f"🌩️ HTTP ERROR: {e}")
                return None

            # 4. Success! Safely unpack JSON
            try:
                return response.json()
            except ValueError:
                print(
                    "❌ ERROR: FRED returned HTTP 200, but response body is not valid JSON."
                )
                return None

        print(
            f"❌ Max retries ({max_retries}) exceeded. API is rate-limiting."
        )
        return None
