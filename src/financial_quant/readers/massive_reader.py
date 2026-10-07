import os
import time
import json
import requests
import pandas as pd
import numpy as pd
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

    def _execute_with_cache(
        self, 
        fetch_callback, 
        ticker: str, 
        start_date: str, 
        end_date: str, 
        resolution: str, 
        market: str = "",
        max_api_lookback_years: float = None
    ):
        """
        Universal self-healing caching engine using Parquet files.
        Lookup Order: Local Cache -> Static_Data_Repo -> API Call (Expanded on Corrupted Ranges)
        
        Handles Free-Tier API limits gracefully:
        1. Pre-cutoff corruptions: Sanitizes locally via ffill().
        2. Post-cutoff corruptions: Expands API fetch range from earliest error to end_date using 1 API call credit.
        """
        safe_ticker = ticker.replace(":", "_")
        filename = f"{safe_ticker}_{resolution}_data.parquet"
        filepath = os.path.join(self.cache_dir, filename)

        # 📅 Determine API tier cutoff date
        lookback_years = max_api_lookback_years if max_api_lookback_years is not None else getattr(self, 'max_api_lookback_years', 2.0)
        api_cutoff_dt = pd.Timestamp.today().normalize() - pd.DateOffset(years=lookback_years)

        df = pd.DataFrame()
        fetch_ranges = []

        # ------------------------------------------------------------------
        # STEP 1: CHECK LOCAL CACHE & IDENTIFY CORRUPTED DATE TAILS
        # ------------------------------------------------------------------
        if os.path.exists(filepath):
            try:
                df = pd.read_parquet(filepath)
                price_cols = [c for c in ['settlement_price', 'close', 'c', 'price', 'settle'] if c in df.columns]
                
                if price_cols:
                    invalid_mask = (df[price_cols] <= 0).any(axis=1) | df[price_cols].isna().any(axis=1)
                    if invalid_mask.any():
                        bad_cached_dates = df.index[invalid_mask]
                        print(f"⚠️ Detected {len(bad_cached_dates)} zero/missing price row(s) in local cache for {ticker}.")
                        
                        fetchable_bad_dates = bad_cached_dates[bad_cached_dates >= api_cutoff_dt]
                        unfetchable_bad_dates = bad_cached_dates[bad_cached_dates < api_cutoff_dt]

                        # 1. Historical data beyond API reach -> ffill locally
                        if len(unfetchable_bad_dates) > 0:
                            print(f"🙈 {len(unfetchable_bad_dates)} row(s) predate the {lookback_years}-yr API limit ({api_cutoff_dt.strftime('%Y-%m-%d')}). Forward-filling locally.")
                            df[price_cols] = df[price_cols].mask(df[price_cols] <= 0, np.nan).ffill().bfill()

                        # 2. Corrupted data within API reach -> Expand API call to refresh everything from min_bad_date onwards
                        if len(fetchable_bad_dates) > 0:
                            earliest_bad_date = fetchable_bad_dates.min().strftime('%Y-%m-%d')
                            print(f"🔄 Expanding API fetch: Refreshing all data from earliest error ({earliest_bad_date}) to {end_date}...")
                            
                            # Trim off the bad tail from the local cache so the fresh API payload seamlessly replaces it
                            df = df[df.index < fetchable_bad_dates.min()]
                            
                            # Force API fetch range from earliest bad date to end_date
                            fetch_ranges.append((earliest_bad_date, end_date))

            except Exception as e:
                print(f"⚠️ Local cache unreadable for {filename}: {e}")
                df = pd.DataFrame()

        # ------------------------------------------------------------------
        # STEP 2: FALLBACK TO STATIC REPO IF LOCAL CACHE IS EMPTY
        # ------------------------------------------------------------------
        if df.empty and not fetch_ranges:
            local_repo_path = os.path.join("Static_Data_Repo", "massive", filename)
            remote_repo_url = f"{self.repo_raw_url}/{filename}"

            print(f"🔍 Cache miss. Checking Static_Data_Repo for {filename}...")

            if os.path.exists(local_repo_path):
                print(f"📦 Found locally at {local_repo_path}")
                try:
                    df = pd.read_parquet(local_repo_path)
                except Exception:
                    df = pd.DataFrame()
            else:
                print(f"🔗 Attempting remote fetch: {remote_repo_url}")
                try:
                    df = pd.read_parquet(remote_repo_url)
                    print(f"🌐 Successfully loaded {ticker} from GitHub!")
                except Exception as e:
                    print(f"⚠️ Remote fetch failed: {e}")
                    df = pd.DataFrame()

        # ------------------------------------------------------------------
        # STEP 3: CALCULATE MISSING DATE DELTAS (IF NOT ALREADY EXPANDED)
        # ------------------------------------------------------------------
        effective_start = max(pd.to_datetime(start_date), api_cutoff_dt).strftime('%Y-%m-%d')

        if df.empty and not fetch_ranges:
            if pd.to_datetime(end_date) >= api_cutoff_dt:
                fetch_ranges.append((effective_start, end_date))
        elif not fetch_ranges:
            req_end = pd.to_datetime(end_date)
            c_start = pd.to_datetime(df.index.min().strftime('%Y-%m-%d'))
            c_end = pd.to_datetime(df.index.max().strftime('%Y-%m-%d'))

            if pd.to_datetime(effective_start) < c_start:
                fetch_ranges.append((effective_start, (c_start - pd.Timedelta(days=1)).strftime('%Y-%m-%d')))
            if req_end > c_end and req_end >= api_cutoff_dt:
                fetch_start = max(c_end + pd.Timedelta(days=1), api_cutoff_dt).strftime('%Y-%m-%d')
                fetch_ranges.append((fetch_start, end_date))

        # ------------------------------------------------------------------
        # STEP 4: RETURN IMMEDIATELY ON FULL CACHE HIT
        # ------------------------------------------------------------------
        if not fetch_ranges:
            if not os.path.exists(filepath) and not df.empty:
                os.makedirs(self.cache_dir, exist_ok=True)
                df.to_parquet(filepath)
                print(f"💾 Cloned static repo data to local Parquet cache for {ticker}.")
            else:
                print(f"⚡ Full cache hit for {ticker} ({resolution}). Loaded cleanly from Parquet.")
                
            return df.loc[start_date:end_date] if not df.empty else None

        # ------------------------------------------------------------------
        # STEP 5: FETCH MISSING / EXPANDED DATA VIA API
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
                    print(f"\n🚨 SDK Server Crash! Hard rate limit hit for {ticker}.")
                    print("😴 Forcing a hard 65-second server-reset penalty...")
                    time.sleep(65)
                    return self._execute_with_cache(
                        fetch_callback, ticker, start_date, end_date, resolution, market=market, max_api_lookback_years=max_api_lookback_years
                    )
                else:
                    print(f"❌ Connection or Parsing error: {e}")

        # ------------------------------------------------------------------
        # STEP 6: MERGE, SANITIZE, AND PERSIST REPAIRED CACHE
        # ------------------------------------------------------------------
        if df_list:
            combined_df = pd.concat(df_list).drop_duplicates().sort_index()
            combined_df = combined_df[~combined_df.index.duplicated(keep='last')]

            # Final safety pass: Clean any residual zero/negative values across the whole dataset
            price_cols = [c for c in ['settlement_price', 'close', 'c', 'price', 'settle'] if c in combined_df.columns]
            for col in price_cols:
                combined_df[col] = combined_df[col].mask(combined_df[col] <= 0, np.nan)
                if combined_df[col].isna().any():
                    combined_df[col] = combined_df[col].ffill().bfill()

            # Stamp metadata timestamp and save clean state to disk
            combined_df['last_fetched'] = pd.Timestamp.now(tz='America/New_York').tz_localize(None)
            os.makedirs(self.cache_dir, exist_ok=True)
            combined_df.to_parquet(filepath)

            true_start = combined_df.index.min().strftime('%Y-%m-%d')
            true_end = combined_df.index.max().strftime('%Y-%m-%d')
            print(f"💾 Merged and saved clean {ticker} data to Parquet cache. (Total Coverage: {true_start} to {true_end})")

            return combined_df.loc[start_date:end_date]

        return df.loc[start_date:end_date] if not df.empty else None
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
