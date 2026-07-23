import os
import sys
import json
import requests
import time
import pandas as pd
from .massive_base import MassiveBase



class MASSIVEReader(MassiveBase):
    def __init__(self, api_key: str = None, key_name: str = "", calls_per_minute: int = 4):
        super(MASSIVEReader, self).__init__(api_key=api_key, key_name=key_name, calls_per_minute=calls_per_minute)

    def _execute_with_cache(self, fetch_callback, ticker, start_date, end_date, resolution):
        """
        Universal caching engine.
        Inherits _check_cache_metadata and _update_cache_metadata from MassiveBase.
        Takes a 'fetch_callback' function to run the actual API call if cache misses.
        """
        safe_ticker = ticker.replace(":", "_")
        cache_id = f"{safe_ticker}_{resolution}"
        filename = f"{cache_id}_data.csv"
        filepath = os.path.join(self.cache_dir, filename)

        # 1. METADATA VALIDATION CHECK (CACHE HIT)
        if os.path.exists(filepath) and self._check_cache_metadata(cache_id, start_date, end_date):
            print(f"✅ Loaded {ticker} ({resolution}) from local metadata-verified cache.")

            df = pd.read_csv(filepath, index_col=0)
            df.index = pd.to_datetime(df.index, errors='coerce',utc=True)
        # Drop unparseable rows
            df = df[df.index.notnull()]
            # Strip timezone if present
            if getattr(df.index, 'tz', None) is not None:
                df.index = df.index.tz_localize(None)

            df = df.sort_index()
            return df.loc[start_date:end_date]

        # 2. CACHE MISS - FETCH FROM API
        print(f"☁️ Downloading {ticker} ({resolution}) via API...")
        self._enforce_speed_limit()

        try:
            df = fetch_callback()

            if df is None or df.empty:
                print(f"⚠️ Cache exist, but no new data for {ticker}.")
                print(f"❗🧐 Make sure you used the correct method.")
                return None

            # If an older slice already existed, merge them together cleanly
            if os.path.exists(filepath):
                old_df = pd.read_csv(filepath, index_col=0)
                old_df.index = pd.to_datetime(old_df.index, errors='coerce',utc=True)
                
                if getattr(old_df.index, 'tz', None) is not None:
                    old_df.index = old_df.index.tz_localize(None)
                    
                df = pd.concat([old_df, df]).drop_duplicates().sort_index()

            # Save data and update global metadata manifest tracking
            df.to_csv(filepath)

            self._update_cache_metadata(cache_id, start_date, end_date)
            print(f"💾 Saved {ticker} data and metadata to cache.")

            df = df.sort_index()
            return df.loc[start_date:end_date]

        except Exception as e:
            if "429" in str(e):
                print(f"\n🚨 SDK Server Crash! The API forcefully rejected {ticker}.")
                print("😴 Forcing a hard 65-second server-reset penalty...")
                time.sleep(65)
                print(f"🔄 Attempting {ticker} one final time...")
                return self._execute_with_cache(fetch_callback, ticker, start_date, end_date, resolution)
            else:
                print(f"❌ Connection or Parsing error: {e}")
                return None

    # =========================================================================
    # STOCKS & EQUITIES PROVIDER METHODS
    # =========================================================================
    def get_stock_data(self, ticker: str, start_date: str, end_date: str, timespan: str = "day", multiplier: int = 1) -> pd.DataFrame:
        print(f"📈 Fetching stock data for {ticker} ({multiplier} {timespan})...")

        def _fetch():
            aggs = self.client.get_aggs(
                ticker=ticker,
                multiplier=multiplier,
                timespan=timespan,
                limit=50000,
                from_=start_date,
                to=end_date
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

        def _fetch():
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
        print(f"🚀 Fetching futures data for {contract_symbol} ({multiplier} {timespan})...")

        def _fetch():
            url = f"https://api.massive.com/futures/v1/aggs/{contract_symbol}"

            massive_timespan = timespan.lower()
            if massive_timespan == "minute":
                massive_timespan = "min"
            elif massive_timespan == "day":
                massive_timespan = "session"

            resolution_string = f"{multiplier}{massive_timespan}"

            params = {
                "resolution": resolution_string,
                "window_start.gte": start_date,
                "window_start.lte": end_date,
                "limit": 50000,
                "sort": "window_start.asc",
                "apiKey": self.api_key
            }

            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            df = pd.DataFrame(data.get("results", []))

            if not df.empty:
                if 'timestamp' in df.columns:
                    time_col = 'timestamp'
                elif 'window_start' in df.columns:
                    time_col = 'window_start'
                else:
                    time_col = 't'

                try:
                    df[time_col] = pd.to_datetime(df[time_col], unit='ns')
                except ValueError:
                    df[time_col] = pd.to_datetime(df[time_col])

                df.set_index(time_col, inplace=True)

                if timespan in ['day', 'week', 'month', 'session']:
                    df.index = df.index.normalize()
                else:
                    if getattr(df.index, 'tz', None) is None:
                        df.index = df.index.tz_localize('UTC')
                    df.index = df.index.tz_convert('America/New_York').tz_localize(None)

            return df

        resolution_label = f"{multiplier}_{timespan}"

        return self._execute_with_cache(
            fetch_callback=_fetch,
            ticker=contract_symbol,
            start_date=start_date,
            end_date=end_date,
            resolution=resolution_label
        )
