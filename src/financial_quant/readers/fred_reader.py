
import json
import os
import requests
import pandas as pd
import datetime as dt
import pandas_datareader.data as web
from .fred_base import FredBase
from financial_quant.security.credentials import secure_key_setup


class FredReader(FredBase):

    def __init__(
        self,
        api_key=None,
        key_name="fred_key",
        github_raw_base=None,
        cache_dir=None,
        enable_github_repo=False,
    ):
        super(FredReader, self).__init__(api_key=api_key, key_name=key_name)
        if cache_dir:
            self.cache_dir = cache_dir

        self.github_raw_base = (
            github_raw_base.rstrip("/") if github_raw_base else None
        )
        self.enable_github_repo = enable_github_repo

    # --- PUBLIC WRAPPER METHOD ---
    def get_series(
        self, series_ids, start_date=None, end_date=None, ttl_days=None
    ):
        """Fetches one or more series and returns them in a single merged DataFrame."""
        if isinstance(series_ids, str):
            series_ids = [series_ids]
        elif not hasattr(series_ids, "__iter__"):
            raise TypeError("series_ids must be a string or an iterable of strings.")

        dataframes = []

        for series_id in series_ids:
            print(f"\n☁️--- Processing {series_id} ---")
            df = self._get_single_series(
                series_id,
                start_date=start_date,
                end_date=end_date,
            )
            if df is not None and not df.empty:
                dataframes.append(df)
            else:
                print(f"⚠️ Skipping {series_id}: No data was returned.")

        if dataframes:
            if len(dataframes) == 1:
                return dataframes[0]
            print("\n🧩 Merging all series into a single DataFrame...")
            combined_df = pd.concat(dataframes, axis=1, join="outer")
            combined_df.sort_index(inplace=True)
            print("✅ Merge complete!")
            return combined_df
        else:
            print("❌ No data could be retrieved.")
            return None

    # --- CORE WORKHORSE METHOD ---
    def _get_single_series(self, series_id, start_date=None, end_date=None):
        filepath = os.path.abspath(
            os.path.join(self.cache_dir, f"{series_id}_fred.parquet")
        )

        cached_df = None
        needs_api_fetch = True
        fetch_start = start_date  # Default to user's requested start date

        # Normalize requested dates to strip time components
        req_start = pd.to_datetime(start_date).normalize() if start_date else None
        req_end = pd.to_datetime(end_date).normalize() if end_date else None

        # --- 1. LOAD LOCAL CACHE (The Source of Truth) ---
        if os.path.exists(filepath):
            try:
                cached_df = pd.read_parquet(filepath)
                cache_start = cached_df.index.min().normalize()
                cache_end = cached_df.index.max().normalize()

                # Do we need older data than the cache has?
                if req_start and req_start < cache_start:
                    print(f"⚠️ Requested start ({req_start.strftime('%Y-%m-%d')}) is older than cache ({cache_start.strftime('%Y-%m-%d')}). Triggering full history backfill...")
                    fetch_start = start_date
                    cached_df = None  # Discard cache memory to trigger a clean, full redownload
                else:
                    # Does the cache already have all the newest data we asked for?
                    if req_end and req_end <= cache_end:
                        print(f"✅ Cache fully satisfies date range. No API fetch needed.")
                        needs_api_fetch = False
                    else:
                        # Delta fetch! Ask only for data 1 day after our cache ends.
                        delta_start = cache_end + pd.Timedelta(days=1)
                        fetch_start = delta_start.strftime("%Y-%m-%d")
                        print(f"📈 Cache ends at {cache_end.strftime('%Y-%m-%d')}. Triggering delta fetch starting from {fetch_start}...")

            except Exception as e:
                print(f"⚠️ Local cache corrupt or unreadable: {e}. Rebuilding from scratch...")
                cached_df = None

        # --- 2. GITHUB STATIC REPO TIER ---
        if cached_df is None and self.enable_github_repo and self.github_raw_base:
            github_url = f"{self.github_raw_base}/{series_id}_fred.parquet"
            print(f"🌐 [Staged Tier] Checking GitHub Repo: {github_url}...")
            try:
                repo_df = pd.read_parquet(github_url)
                print(f"✅ Found {series_id} in GitHub Repo! Caching locally...")
                os.makedirs(self.cache_dir, exist_ok=True)
                repo_df.to_parquet(filepath)
                cached_df = repo_df
                
                # Verify if repo data is fresh enough, otherwise we still delta fetch
                cache_end = cached_df.index.max().normalize()
                if req_end and req_end <= cache_end:
                    needs_api_fetch = False
                else:
                    delta_start = cache_end + pd.Timedelta(days=1)
                    fetch_start = delta_start.strftime("%Y-%m-%d")
                    needs_api_fetch = True
            except Exception as e:
                print(f"ℹ️ GitHub Repo bypass/fail ({e}). Proceeding to API tier...")
        
        # --- 3. LIVE API FETCH (Delta or Full) ---
        if needs_api_fetch:
            print(f"☁️ Pinging API for {series_id} from {fetch_start or 'beginning'}...")
            try:
                new_df = None
                if self.api_key is None:
                    new_df = web.DataReader(
                        series_id, "fred", start=fetch_start, end=end_date
                    )
                else:
                    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={self.api_key}&file_type=json"
                    if fetch_start:
                        url += f"&observation_start={fetch_start}"
                    if end_date:
                        url += f"&observation_end={end_date}"

                    data = self._make_api_request(url)
                    if data and "observations" in data and len(data["observations"]) > 0:
                        new_df = pd.DataFrame(data["observations"])
                        new_df["DATE"] = pd.to_datetime(new_df["date"])
                        new_df[series_id] = pd.to_numeric(new_df["value"], errors="coerce")
                        new_df = new_df.set_index("DATE")[[series_id]]
                        new_df.dropna(inplace=True)

                # Process the newly downloaded data
                if new_df is not None and not new_df.empty:
                    if cached_df is not None:
                        # Concat new data, overwriting any duplicate dates just in case
                        combined_df = pd.concat([cached_df, new_df])
                        combined_df = combined_df[~combined_df.index.duplicated(keep='last')].sort_index()
                    else:
                        combined_df = new_df.sort_index()

                    # Save the master dataset back to Parquet
                    os.makedirs(self.cache_dir, exist_ok=True)
                    combined_df.to_parquet(filepath)
                    print(f"✅ Success! Saved updated Parquet data to {filepath}.")
                    cached_df = combined_df
                else:
                    print("🤷 No new data returned from API (Treasury boys might be off!). Using existing cache.")

            except Exception as e:
                print(f"❌ An error occurred in API fetch: {e}")
                # We don't crash here; we just fall back to cached_df if we have one.

        # --- 4. FILTER AND RETURN ---
        if cached_df is None or cached_df.empty:
            return None

        final_df = cached_df.copy()
        
        # Finally, slice the dataframe to match exactly what the user asked for
        if req_start:
            final_df = final_df[final_df.index >= req_start]
        if req_end:
            final_df = final_df[final_df.index <= req_end]

        return final_df
