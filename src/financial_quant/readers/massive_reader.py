import os
import time
import json
import requests
import pandas as pd
import pandas_market_calendars as mcal
from .massive_base import MassiveBase


class MASSIVEReader(MassiveBase):
    def __init__(self, api_key: str = None, key_name: str = "", calls_per_minute: int = 4, github_user_or_org: str = "YOUR_GITHUB_USERNAME"):
        super().__init__(api_key=api_key, key_name=key_name, calls_per_minute=calls_per_minute)

        # 📅 Initialize market calendars once for the whole class
        self.cme_cal = mcal.get_calendar('CME_TradeDate')   # For Futures
        self.nyse_cal = mcal.get_calendar('NYSE')           # For Stocks

        # 🌐 Base GitHub URL for static repository fallback
        self.github_user_or_org = github_user_or_org
        self.repo_raw_url = f"https://raw.githubusercontent.com/PatrickJHess/Static_Data_Repo/main/massive"

    def _align_trade_dates(self, start_date: str, end_date: str, market: str = "CME") -> tuple:
        """
        Universal calendar logic to snap weekends and holidays to valid trade dates.
        Prevents phantom cache misses and needless API calls.
        """
        cal = self.cme_cal if market == "CME" else self.nyse_cal

        # Snap start date FORWARD to the next valid trading day
        valid_starts = cal.valid_days(start_date, pd.to_datetime(start_date) + pd.Timedelta(days=15))
        aligned_start = valid_starts[0].strftime('%Y-%m-%d')

        # Snap end date BACKWARD to the most recent valid trading day
        end_dt = pd.to_datetime(end_date).normalize()
        today = pd.Timestamp.today().normalize()

        # Cap at today first
        capped_end_dt = min(end_dt, today)

        # Query calendar using capped_end_dt
        valid_ends = cal.valid_days(capped_end_dt - pd.Timedelta(days=15), capped_end_dt)
        aligned_end = valid_ends[-1].strftime('%Y-%m-%d')

        return aligned_start, aligned_end
    def _execute_with_cache(self, fetch_callback, ticker, start_date, end_date, resolution, market=""):
        """
        Universal caching engine using Parquet files.
        Lookup Order: Local Cache -> Static_Data_Repo (Local Clone -> GitHub) -> API Call (Missing Deltas)
        """
        safe_ticker = ticker.replace(":", "_")
        filename = f"{safe_ticker}_{resolution}_data.parquet"
        filepath = os.path.join(self.cache_dir, filename)

        df = pd.DataFrame()

        # ------------------------------------------------------------------
        # STEP 1: CHECK LOCAL CACHE
        # ------------------------------------------------------------------
        if os.path.exists(filepath):
            try:
                df = pd.read_parquet(filepath)
                print(f"📁 Loaded {ticker} ({resolution}) from local Parquet cache.")
            except Exception:
                df = pd.DataFrame()

        # ------------------------------------------------------------------
        # STEP 2: FALLBACK TO STATIC DATA REPO (LOCAL OR GITHUB)
        # ------------------------------------------------------------------
        if df.empty:
            local_repo_path = os.path.join("Static_Data_Repo", "massive", filename)
            remote_repo_url = f"{self.repo_raw_url}/{filename}"

            print(f"🔍 Cache miss. Checking Static_Data_Repo for {filename}...")

            if os.path.exists(local_repo_path):
                print(f"📦 Found locally at {local_repo_path}")
            else:
                print(f"🔗 Attempting remote fetch: {remote_repo_url}")
                try:
                    df = pd.read_parquet(remote_repo_url)
                    print(f"🌐 Successfully loaded {ticker} from GitHub!")
                except Exception as e:
                    print(f"⚠️ Remote fetch failed: {e}")
                    df = pd.DataFrame()
        # ------------------------------------------------------------------
        # STEP 3: CALCULATE MISSING DATE DELTAS
        # ------------------------------------------------------------------
        fetch_ranges = []

        if df.empty:
            # Complete miss: fetch full requested window
            fetch_ranges.append((start_date, end_date))
        else:
            req_start = pd.to_datetime(start_date)
            req_end = pd.to_datetime(end_date)
            c_start = pd.to_datetime(df.index.min().strftime('%Y-%m-%d'))
            c_end = pd.to_datetime(df.index.max().strftime('%Y-%m-%d'))

            # Gap BEFORE cached range
            if req_start < c_start:
                fetch_end = (c_start - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
                fetch_ranges.append((start_date, fetch_end))

            # Gap AFTER cached range
            if req_end > c_end:
                fetch_start = (c_end + pd.Timedelta(days=1)).strftime('%Y-%m-%d')

                # Check valid trading days using the appropriate market calendar
                cal = self.cme_cal if market == "CME" else self.nyse_cal
                missing_bdays = len(cal.valid_days(start_date=fetch_start, end_date=end_date))

                if missing_bdays > 0:
                    fetch_ranges.append((fetch_start, end_date))
                else:
                    market_name = "CME" if market == "CME" else "NYSE"
                    print(f"✅ Gap ({fetch_start} to {end_date}) contains no valid {market_name} trading days. Skipping API call.")

        # ------------------------------------------------------------------
        # STEP 4: RETURN IMMEDIATELY ON FULL CACHE HIT
        # ------------------------------------------------------------------
        if not fetch_ranges:
            # If the local cache file doesn't exist, we must have loaded from the static repo. 
            # Save it locally so we don't have to hit the repo again next time.
            if not os.path.exists(filepath):
                os.makedirs(self.cache_dir, exist_ok=True)
                df.to_parquet(filepath)
                print(f"💾 Cloned static repo data to local Parquet cache for {ticker}.")
            else:
                print(f"⚡ Full cache hit for {ticker} ({resolution}). Loaded directly from Parquet.")
                
            return df.loc[start_date:end_date]

        # ------------------------------------------------------------------
        # STEP 5: FETCH MISSING DELTAS VIA API
        # ------------------------------------------------------------------
        df_list = [df] if not df.empty else []

        for f_start, f_end in fetch_ranges:
            print(f"☁️ Downloading {ticker} ({resolution}) via API from {f_start} to {f_end}...")
            self._enforce_speed_limit()

            try:
                new_data = fetch_callback(f_start, f_end)
                if new_data is not None and not new_data.empty:
                    df_list.append(new_data)

            except Exception as e:
                if "429" in str(e):
                    print(f"\n🚨 SDK Server Crash! The API forcefully rejected {ticker}.")
                    print("😴 Forcing a hard 65-second server-reset penalty...")
                    time.sleep(65)
                    print(f"🔄 Attempting {ticker} one final time...")
                    return self._execute_with_cache(
                        fetch_callback, ticker, start_date, end_date, resolution, market=market
                    )
                else:
                    print(f"❌ Connection or Parsing error: {e}")
                    return None

        # ------------------------------------------------------------------
        # STEP 6: MERGE, CLEAN, AND SAVE TO LOCAL CACHE
        # ------------------------------------------------------------------
        if len(df_list) == (1 if not df.empty else 0):
            print(f"⚠️ API returned no new data for requested ranges.")
            return df.loc[start_date:end_date] if not df.empty else None

        combined_df = pd.concat(df_list).drop_duplicates().sort_index()
        combined_df = combined_df[~combined_df.index.duplicated(keep='last')]

        # Ensure local cache folder exists and save as Parquet
        os.makedirs(self.cache_dir, exist_ok=True)
        combined_df.to_parquet(filepath)

        true_start = combined_df.index.min().strftime('%Y-%m-%d')
        true_end = combined_df.index.max().strftime('%Y-%m-%d')
        print(f"💾 Merged and saved {ticker} to Parquet cache. (Total Coverage: {true_start} to {true_end})")

        return combined_df.loc[start_date:end_date]
    # =========================================================================
    # STOCKS & EQUITIES PROVIDER METHODS
    # =========================================================================
    def get_stock_data(self, ticker: str, start_date: str, end_date: str, timespan: str = "day", multiplier: int = 1) -> pd.DataFrame:
        # 🛡️ Clean the dates before anything else!
        if timespan.lower() in ["day", "daily", "session"]:
            start_date, end_date = self._align_trade_dates(start_date, end_date, market="NYSE")

        print(f"📈 Fetching stock data for {ticker} ({multiplier} {timespan})...")

        def _fetch(f_start, f_end):
            aggs = self.client.get_aggs(
                ticker=ticker,
                multiplier=multiplier,
                timespan=timespan,
                limit=50000,
                from_=f_start,
                to=f_end
            )
            df = pd.DataFrame(aggs)
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                df.index = df.index.tz_localize('UTC').tz_convert('America/New_York').tz_localize(None)
            return df

        resolution_label = f"{multiplier}_{timespan}"

        return self._execute_with_cache(
            fetch_callback=_fetch,
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            resolution=resolution_label
        )


    # =========================================================================
    # DIVIDENDS PROVIDER METHOD
    # =========================================================================
    def get_dividend_data(self, ticker: str, start_date: str = "1970-01-01", end_date: str = "2099-12-31") -> pd.DataFrame:
        print(f"💰 Fetching dividend data for {ticker}...")

        def _fetch(f_start, f_end):
            url = "https://api.massive.com/stocks/v1/dividends"
            params = {
                "ticker": ticker,
                "limit": 1000,
                "sort": "ex_dividend_date.asc",
                "apiKey": self.api_key
            }

            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            df = pd.DataFrame(data.get("results", []))

            if not df.empty:
                time_col = 'ex_dividend_date'
                if time_col in df.columns:
                    df[time_col] = pd.to_datetime(df[time_col])
                    df.set_index(time_col, inplace=True)
                    df.index = df.index.normalize()
            return df

        return self._execute_with_cache(
            fetch_callback=_fetch,
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            resolution="dividends"
        )


    # =========================================================================
    # FUTURES PROVIDER METHODS
    # =========================================================================
    def get_futures_data(self, contract_symbol: str, start_date: str, end_date: str, timespan: str = "day", multiplier: int = 1) -> pd.DataFrame:
        is_daily_resolution = timespan.lower() in ["day", "daily", "session"]

        # 🛡️ Clean the dates before anything else!
        if is_daily_resolution:
            start_date, end_date = self._align_trade_dates(start_date, end_date, market="CME")

        print(f"🚀 Fetching futures data for {contract_symbol} ({multiplier} {timespan})...")

        def _fetch(f_start, f_end):
            url = f"https://api.massive.com/futures/v1/aggs/{contract_symbol}"

            # 1. Apply start-date shift ONLY to daily/session data
            if is_daily_resolution:
                massive_timespan = "session"
                api_start = (pd.to_datetime(f_start) - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                 massive_timespan = "min" if timespan.lower() == "minute" else timespan.lower()
                 # Intraday bars (1_min, 5_min, 60_min) keep exact start boundary
                 api_start = f_start

            # Guaranteed end-date buffer for both resolutions
            api_end = (pd.to_datetime(f_end) + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            resolution_string = f"{multiplier}{massive_timespan}"

            params = {
                "resolution": resolution_string,
                "window_start.gte": api_start,
                "window_start.lte": api_end,
                "limit": 50000,
                "sort": "window_start.asc",
                "apiKey": self.api_key
            }

            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            df = pd.DataFrame(data.get("results", []))

            if not df.empty:
                time_col = 'timestamp' if 'timestamp' in df.columns else ('window_start' if 'window_start' in df.columns else 't')

                try:
                    df[time_col] = pd.to_datetime(df[time_col], unit='ns')
                except ValueError:
                    df[time_col] = pd.to_datetime(df[time_col])

                df.set_index(time_col, inplace=True)

                # 2. Map evening window_start times (18:00) to the Trade Date ONLY for daily bars
                if timespan in ['day', 'week', 'month', 'session']:
                    # Massive API stamps daily futures bars at session open (the evening before).
                    # Shift all daily/session timestamps forward 1 day to match the Trade Date.
                    df.index = (df.index + pd.Timedelta(days=1)).normalize()
                else:
                    if getattr(df.index, 'tz', None) is None:
                        df.index = df.index.tz_localize('UTC')
                    df.index = df.index.tz_convert('America/New_York').tz_localize(None)

            df = df.rename(columns={'ticker':'Symbol'})
            return df

        resolution_label = f"{multiplier}_{timespan}"

        return self._execute_with_cache(
            fetch_callback=_fetch,
            ticker=contract_symbol,
            start_date=start_date,
            end_date=end_date,
            resolution=resolution_label
        )
