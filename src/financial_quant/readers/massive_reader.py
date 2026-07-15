import os
import sys
import json
import requests
import time
import pandas as pd
from .massive_base import MassiveBase



class MASSIVEReader(MassiveBase):
    def __init__(self, api_key: str = None, key_name: str = "", calls_per_minute: int = 4):
      """
          Main interface for fetching historical OHLCV data for Stocks and Futures.

          Inherits from `MassiveBase` to utilize a robust local caching engine, 
          automatic rate-limit handling, and secure API key management. This reader 
          intelligently parses multi-format timestamps (milliseconds vs. 19-digit nanoseconds) 
          and normalizes all intraday data to US Eastern Time (America/New_York) while 
          keeping daily/weekly session dates timezone-naive to prevent date-shifting bugs.

          Key Features:
              - Smart Caching: Saves data to disk (or Google Drive in Colab). Automatically 
                merges new API data with old local data to minimize bandwidth.
              - Timezone Correction: Aligns intraday timestamps to the Wall Street 9:30 AM 
                opening bell, natively handling Daylight Saving Time adjustments.
              - Dynamic Routing: Seamlessly translates standard Polygon timespans (e.g., 'minute') 
                into Massive's custom backend architecture (e.g., '15min', 'session').

          Args:
              api_key (str, optional): Direct string of the Massive/Polygon API key. Defaults to None.
              key_name (str, optional): The environment variable name to search for if api_key 
                  is None (e.g., "MASSIVE_KEY"). Defaults to "".
              calls_per_minute (int, optional): The maximum number of API calls allowed per minute 
                  before the engine forces a cooldown sleep. Defaults to 4.

          Example:
              >>> reader = MASSIVEReader(key_name="MASSIVE_API_KEY")
              >>> 
              >>> # Fetch 15-minute futures data
              >>> df_futures = reader.get_futures_data("ESM6", "2026-06-01", "2026-06-18", timespan="minute", multiplier=15)
              >>> 
              >>> # Fetch Daily stock data
              >>> df_stocks = reader.get_stock_data("AAPL", "2020-01-01", "2026-01-01", timespan="day", multiplier=1)
        """
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
        
        # Inherited _check_cache_metadata
        if os.path.exists(filepath) and self._check_cache_metadata(cache_id, start_date, end_date):
            print(f"✅ Loaded {ticker} ({resolution}) from local metadata-verified cache.")

            # --- THE FIX: Clean read, no timezone conversion! ---
            df = pd.read_csv(filepath, index_col=0, parse_dates=True)

            # Optional legacy sanitizer just in case
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            df = df.sort_index()
            return df.loc[start_date:end_date]

        # 2. CACHE MISS - FETCH FROM API
        print(f"☁️ Downloading {ticker} ({resolution}) via API...")
        self._enforce_speed_limit()

        try:
            # Execute the specific API logic passed from the parent function
            # Cache is missing or incomplete API call made from stock or futures method
            df = fetch_callback()

            if df is None or df.empty:
                print(f"⚠️ Cache exist, but no new data for {ticker}.")
                print(f"❗🧐 Make sure you used the correct method.")
                return None

            # If an older slice already existed, merge them together cleanly
            if os.path.exists(filepath):
                old_df = pd.read_csv(filepath, index_col=0, parse_dates=True)
      #          old_df.index = pd.to_datetime(old_df.index, utc=True).tz_convert('America/New_York')
                if old_df.index.tz is not None:
                   old_df.index = old_df.index.tz_localize(None)
                df = pd.concat([old_df, df]).drop_duplicates().sort_index()

            # Save data and update global metadata manifest tracking
            df.to_csv(filepath)

            # Inerited _update_cache_metadata
            self._update_cache_metadata(cache_id, start_date, end_date)
            print(f"💾 Saved {ticker} data and metadata to cache.")

            df = df.sort_index()
            # Slice frame locally to return the exact subset requested
            return df.loc[start_date:end_date]

        except Exception as e:
            if "429" in str(e):
                print(f"\n🚨 SDK Server Crash! The API forcefully rejected {ticker}.")
                print("😴 Forcing a hard 65-second server-reset penalty...")
                time.sleep(65)
                print(f"🔄 Attempting {ticker} one final time...")
                # Recursive retry
                return self._execute_with_cache(fetch_callback, ticker, start_date, end_date, resolution)
            else:
                print(f"❌ Connection or Parsing error: {e}")
                return None

    # =========================================================================
    # STOCKS & EQUITIES PROVIDER METHODS
    # =========================================================================
    def get_stock_data(self, ticker: str, start_date: str, end_date: str, timespan: str = "day", multiplier: int = 1) -> pd.DataFrame:
        """
        Pulls OHLCV historical data dynamically.
        Examples:
          - 1 Day: timespan="day", multiplier=1
          - 15 Min: timespan="minute", multiplier=15
          - 1 Month: timespan="month", multiplier=1
           - return is the callback function _fetch()
        """
        print(f"📈 Fetching stock data for {ticker} ({multiplier} {timespan})...")

        def _fetch():
            aggs = self.client.get_aggs(
                ticker=ticker,
                multiplier=multiplier,
                timespan=timespan,
                limit=50000, # Maximize the payload limit
                from_=start_date,
                to=end_date
            )
            df = pd.DataFrame(aggs)
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)

                # 2. Localize to UTC, then convert to Wall Street time (EST/EDT)
                df.index = df.index.tz_localize('UTC').tz_convert('America/New_York').tz_localize(None)
            return df

        # Create a unique cache ID like "1_day" or "15_minute"
        resolution_label = f"{multiplier}_{timespan}"

        return self._execute_with_cache(
            fetch_callback=_fetch,
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            resolution=resolution_label
        )

    # =========================================================================
    # FUTURES PROVIDER METHODS
    # =========================================================================
    def get_futures_data(self, contract_symbol: str, start_date: str, end_date: str, timespan: str = "day", multiplier: int = 1) -> pd.DataFrame:
        """
        Pulls OHLCV historical data dynamically for futures using a custom endpoint.
        - return is the callback function _fetch()
        """
        print(f"🚀 Fetching futures data for {contract_symbol} ({multiplier} {timespan})...")

        def _fetch():
            # 1. Use the Massive base URL
            url = f"https://api.massive.com/futures/v1/aggs/{contract_symbol}"

            # 2. Translate standard timespans into Massive's required abbreviations
            massive_timespan = timespan.lower()
            if massive_timespan == "minute":
                massive_timespan = "min"
            elif massive_timespan == "day":
                massive_timespan = "session"

            # e.g., combines 15 and "min" into "15min"
            resolution_string = f"{multiplier}{massive_timespan}"

            # 3. Package the query parameters EXACTLY how Massive's docs require them
            params = {
                "resolution": resolution_string,
                "window_start.gte": start_date,
                "window_start.lte": end_date,
                "limit": 50000,               # Maximize the payload limit
                "sort": "window_start.asc",   # Ensure chronological order
                "apiKey": self.api_key
            }

            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            df = pd.DataFrame(data.get("results", []))

            if not df.empty:
                # Find the correct time column
                if 'timestamp' in df.columns:
                    time_col = 'timestamp'
                elif 'window_start' in df.columns:
                    time_col = 'window_start'
                else:
                    time_col = 't'

                # Parse Massive's 19-digit nanosecond timestamps
                try:
                    df[time_col] = pd.to_datetime(df[time_col], unit='ns')
                except ValueError:
                    df[time_col] = pd.to_datetime(df[time_col])

                df.set_index(time_col, inplace=True)

                # --- TIMEZONE SHIFT ---
                if timespan in ['day', 'week', 'month', 'session']:
                    # Keep Daily data pure (removes the 20:00:00 midnight shift bug)
                    df.index = df.index.normalize()
                else:
                    # Intraday data perfectly shifts to New York time
                    if df.index.tz is None:
                        df.index = df.index.tz_localize('UTC')
                    df.index = df.index.tz_convert('America/New_York').tz_localize(None)

            return df

        resolution_label = f"{multiplier}_{timespan}"

        # Hand it off to the exact same cache engine!
        return self._execute_with_cache(
            fetch_callback=_fetch,
            ticker=contract_symbol,
            start_date=start_date,
            end_date=end_date,
            resolution=resolution_label
        )
