
import json
import os
import requests
import pandas as pd
import pandas_datareader.data as web
from .fred_base import FredBase
from financial_quant.security.credentials import secure_key_setup

class FredReader(FredBase):
    def __init__(self, api_key=None, key_name="fred_key"):
        """
        Main interface for fetching economic data from FRED.
        Inherits authentication and caching directories from FredBase.
        """
        super(FredReader,self).__init__(api_key=api_key, key_name=key_name)

    # --- PUBLIC WRAPPER METHOD ---
    def get_series(self, series_ids, start_date=None, end_date=None, ttl_days=7):
        """Fetches one or more series and returns them in a single merged DataFrame."""
        if isinstance(series_ids, str):
            series_ids = [series_ids]
        elif not hasattr(series_ids, '__iter__'):
            raise TypeError("series_ids must be a string or an iterable of strings.")

        dataframes = []

        for series_id in series_ids:
            print(f"\n☁️--- Processing {series_id} ---")

            df = self._get_single_series(series_id, start_date=start_date, end_date=end_date, ttl_days=ttl_days)
            if df is not None and not df.empty:
                dataframes.append(df)
            else:
                print(f"⚠️ Skipping {series_id}: No data was returned.")

        if dataframes:
            if len(dataframes) == 1:
                return dataframes[0]
            print("\n🧩 Merging all series into a single DataFrame...")
            combined_df = pd.concat(dataframes, axis=1, join='outer')
            combined_df.sort_index(inplace=True)
            print("✅ Merge complete!")
            return combined_df
        else:
            print("❌ No data could be retrieved.")
            return None

    # --- CORE WORKHORSE METHOD ---
    def _get_single_series(self, series_id, start_date=None, end_date=None, ttl_days=7):
        import datetime as dt
        series_dir = os.path.join(self.cache_dir, series_id)

        filepath = os.path.abspath(os.path.join(series_dir, f"{series_id}_fred.csv"))
        metadata_file = os.path.abspath(os.path.join(series_dir, "cache_metadata.json"))

        metadata = {}
        metadata_is_stale = True
        metadata_updated_this_run = False

        # --- NESTED METADATA HELPER ---
        def update_metadata():
            nonlocal metadata, metadata_updated_this_run
            if not self.api_key: return True
            
            meta_url = f"https://api.stlouisfed.org/fred/series?series_id={series_id}&api_key={self.api_key}&file_type=json"
            try:
                meta_data = self._make_api_request(meta_url, series_id=series_id)
                
                if not meta_data:
                    return False

                if 'seriess' in meta_data and len(meta_data['seriess']) > 0:
                    series_info = meta_data['seriess'][0]
                    metadata['series_inception'] = series_info.get('observation_start')
                    metadata['series_last_observed'] = series_info.get('observation_end')
                    metadata['title'] = series_info.get('title')
                    metadata['frequency'] = series_info.get('frequency')
                    metadata['last_updated'] = dt.datetime.now(dt.timezone.utc).isoformat()
                    
                    os.makedirs(series_dir, exist_ok=True)

                    with open(metadata_file, 'w') as f:
                        json.dump(metadata, f, indent=4)
                    
                    metadata_updated_this_run = True
                    print("⏳ Metadata synced and timestamp updated.")
                    return True
            except Exception as e:
                print(f"⚠️ Could not update metadata: {e}")
                return False

        # --- 1. READ LOCAL METADATA ---
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
            except (json.JSONDecodeError, ValueError) as e:
                print(f"⚠️ Warning: Corrupt or empty metadata cache found for {series_id}. Resetting file...")
                metadata = {}
                try:
                    os.remove(metadata_file) 
                except Exception:
                    pass
                
            if 'last_updated' in metadata:
                last_updated = dt.datetime.fromisoformat(metadata['last_updated'])
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=dt.timezone.utc)
                
                days_old = (dt.datetime.now(dt.timezone.utc) - last_updated).days
                
                if days_old < ttl_days:
                    metadata_is_stale = False
                    print(f"🕒 Metadata is fresh ({days_old} days old).")
                else:
                    print(f"⏳ Metadata is {days_old} days old (TTL: {ttl_days}). It's stale.")

        # --- 2. SMART PING ---
        if not metadata:
            print(f"🆕 First run for {series_id}. Initializing metadata...")
            if not update_metadata():
              return None

        elif self.api_key and end_date and 'series_last_observed' in metadata and metadata_is_stale:
            if pd.to_datetime(end_date) > pd.to_datetime(metadata['series_last_observed']):
                print(f"🔎 Requested date exceeds known end date. Checking for updates...")
                update_metadata()

        # --- 3. CLAMP DATES ---
        if 'series_inception' in metadata and start_date:
            clamped_start = max(pd.to_datetime(start_date), pd.to_datetime(metadata['series_inception']))
            if pd.to_datetime(start_date) < clamped_start:
                start_date = clamped_start.strftime('%Y-%m-%d')
                print(f'⚠️ Adjusted start date to First Available Data: {start_date}')

        if 'series_last_observed' in metadata and end_date:
            clamped_end = min(pd.to_datetime(end_date), pd.to_datetime(metadata['series_last_observed']))
            if pd.to_datetime(end_date) > clamped_end:
                end_date = clamped_end.strftime('%Y-%m-%d')
                print(f'⚠️ FRED has no data past {end_date}. Adjusted request to match.')

        # --- 4. CHECK LOCAL CACHE ---
        cache_valid = False
        cache_start = None
        cache_end = None

        if os.path.exists(filepath):
            cache_valid = True

            if metadata_is_stale:
                cache_valid = False
                print(f"♻️ TTL expired. Forcing data and metadata refresh for {series_id}...")

            if cache_valid:
                if 'cache_start' in metadata and 'cache_end' in metadata:
                    cache_start = pd.to_datetime(metadata['cache_start'])
                    cache_end = pd.to_datetime(metadata['cache_end'])
                else:
                    try:
                        temp_df = pd.read_csv(filepath, index_col='DATE', parse_dates=True)
                        if not temp_df.empty:
                            cache_start = temp_df.index.min()
                            cache_end = temp_df.index.max()
                        else:
                            cache_valid = False
                    except Exception:
                        cache_valid = False

                if cache_valid and cache_start is not None:
                    if start_date and pd.to_datetime(start_date) < cache_start:
                        if len(pd.bdate_range(start_date, cache_start, inclusive='left')) > 0:
                            cache_valid = False

                    if end_date and pd.to_datetime(end_date) > cache_end:
                        freq_str = metadata.get('frequency', '')
                        if 'Annual' in freq_str:
                            cache_end_coverage = cache_end + pd.DateOffset(years=1) - pd.Timedelta(days=1)
                        elif 'Quarterly' in freq_str:
                            cache_end_coverage = cache_end + pd.DateOffset(months=3) - pd.Timedelta(days=1)
                        elif 'Monthly' in freq_str:
                            cache_end_coverage = cache_end + pd.DateOffset(months=1) - pd.Timedelta(days=1)
                        elif 'Weekly' in freq_str:
                            cache_end_coverage = cache_end + pd.Timedelta(days=6)
                        else:
                            cache_end_coverage = cache_end 
                        
                        if pd.to_datetime(end_date) > cache_end_coverage:
                            cache_valid = False

            if cache_valid:
                print(f"✅ Loaded {series_id} from local cache.")
                df = pd.read_csv(filepath, index_col='DATE', parse_dates=True)
                if start_date:
                    df = df[df.index >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[df.index <= pd.to_datetime(end_date)]
                return df
            else:
                print(f"♻️ Cache missing or insufficient bounds. Killing cache for {series_id}...")
                try:
                    os.remove(filepath)
                except OSError:
                    pass
                
                keys_removed = False
                if 'cache_start' in metadata:
                    del metadata['cache_start']
                    keys_removed = True
                if 'cache_end' in metadata:
                    del metadata['cache_end']
                    keys_removed = True
                
                if keys_removed:
                    with open(metadata_file, 'w') as f:
                        json.dump(metadata, f, indent=4)

        # --- 5. API FETCH ---
        print(f"☁️ Fetching fresh {series_id} observations...")
        if not metadata_updated_this_run and metadata_is_stale:
            if not update_metadata():
              return None

        try:
            if self.api_key is None:
                print("⚠️ No API key found. Defaulting to pandas_datareader...")
                df = web.DataReader(series_id, 'fred', start=start_date, end=end_date)
            else:
                url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={self.api_key}&file_type=json"
                if start_date: url += f"&observation_start={start_date}"
                if end_date: url += f"&observation_end={end_date}"

                safe_url = url.replace(self.api_key, "HIDDEN_KEY")
                print(f"📡 Sending URL to FRED: {safe_url}")

                data = self._make_api_request(url)

                if not data or 'observations' not in data:
                  print(f"❌ API Error: Could not retrieve observation data for {series_id}.")
                  return None

                df = pd.DataFrame(data['observations'])
                df['DATE'] = pd.to_datetime(df['date'])
                df[series_id] = pd.to_numeric(df['value'], errors='coerce')
                df = df.set_index('DATE')
                df = df[[series_id]]

            df.dropna(inplace=True)
            
            os.makedirs(series_dir, exist_ok=True)            
 
            df.to_csv(filepath)
            
            if not df.empty:
                metadata['cache_start'] = df.index.min().strftime('%Y-%m-%d')
                metadata['cache_end'] = df.index.max().strftime('%Y-%m-%d')
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=4)
                    
            print(f"Success! Data saved to {filepath}.")
            return df

        except Exception as e:
            print(f"❌ An error occurred: {e}")
            return None 



class FredReader(FredBase):
    def __init__(self, api_key=None, key_name="fred_key"):
        """
        Main interface for fetching economic data from FRED.
        Inherits authentication and caching directories from FredBase.
        """
        super(FredReader,self).__init__(api_key=api_key, key_name=key_name)

    # --- PUBLIC WRAPPER METHOD ---
    def get_series(self, series_ids, start_date=None, end_date=None, ttl_days=7):
        """Fetches one or more series and returns them in a single merged DataFrame."""
        if isinstance(series_ids, str):
            series_ids = [series_ids]
        elif not hasattr(series_ids, '__iter__'):
            raise TypeError("series_ids must be a string or an iterable of strings.")

        dataframes = []

        for series_id in series_ids:
            print(f"\n☁️--- Processing {series_id} ---")

            df = self._get_single_series(series_id, start_date=start_date, end_date=end_date, ttl_days=ttl_days)
            if df is not None and not df.empty:
                dataframes.append(df)
            else:
                print(f"⚠️ Skipping {series_id}: No data was returned.")

        if dataframes:
            if len(dataframes) == 1:
                return dataframes[0]
            print("\n🧩 Merging all series into a single DataFrame...")
            combined_df = pd.concat(dataframes, axis=1, join='outer')
            combined_df.sort_index(inplace=True)
            print("✅ Merge complete!")
            return combined_df
        else:
            print("❌ No data could be retrieved.")
            return None

    # --- CORE WORKHORSE METHOD ---
    def _get_single_series(self, series_id, start_date=None, end_date=None, ttl_days=7):
        import datetime as dt
        
        # Eliminated series_dir. Saving directly to the root cache_dir.
        filepath = os.path.abspath(os.path.join(self.cache_dir, f"{series_id}_fred.csv"))
        # Namespaced the metadata file to prevent collisions in the shared root directory
        metadata_file = os.path.abspath(os.path.join(self.cache_dir, f"{series_id}_metadata.json"))

        metadata = {}
        metadata_is_stale = True
        metadata_updated_this_run = False

        # --- NESTED METADATA HELPER ---
        def update_metadata():
            nonlocal metadata, metadata_updated_this_run
            if not self.api_key: return True
            
            meta_url = f"https://api.stlouisfed.org/fred/series?series_id={series_id}&api_key={self.api_key}&file_type=json"
            try:
                meta_data = self._make_api_request(meta_url, series_id=series_id)
                
                if not meta_data:
                    return False

                if 'seriess' in meta_data and len(meta_data['seriess']) > 0:
                    series_info = meta_data['seriess'][0]
                    metadata['series_inception'] = series_info.get('observation_start')
                    metadata['series_last_observed'] = series_info.get('observation_end')
                    metadata['title'] = series_info.get('title')
                    metadata['frequency'] = series_info.get('frequency')
                    metadata['last_updated'] = dt.datetime.now(dt.timezone.utc).isoformat()
                    
                    os.makedirs(self.cache_dir, exist_ok=True)

                    with open(metadata_file, 'w') as f:
                        json.dump(metadata, f, indent=4)
                    
                    metadata_updated_this_run = True
                    print("⏳ Metadata synced and timestamp updated.")
                    return True
            except Exception as e:
                print(f"⚠️ Could not update metadata: {e}")
                return False

        # --- 1. READ LOCAL METADATA ---
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
            except (json.JSONDecodeError, ValueError) as e:
                print(f"⚠️ Warning: Corrupt or empty metadata cache found for {series_id}. Resetting file...")
                metadata = {}
                try:
                    os.remove(metadata_file) 
                except Exception:
                    pass
                
            if 'last_updated' in metadata:
                last_updated = dt.datetime.fromisoformat(metadata['last_updated'])
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=dt.timezone.utc)
                
                days_old = (dt.datetime.now(dt.timezone.utc) - last_updated).days
                
                if days_old < ttl_days:
                    metadata_is_stale = False
                    print(f"🕒 Metadata is fresh ({days_old} days old).")
                else:
                    print(f"⏳ Metadata is {days_old} days old (TTL: {ttl_days}). It's stale.")

        # --- 2. SMART PING ---
        if not metadata:
            print(f"🆕 First run for {series_id}. Initializing metadata...")
            if not update_metadata():
              return None

        elif self.api_key and end_date and 'series_last_observed' in metadata and metadata_is_stale:
            if pd.to_datetime(end_date) > pd.to_datetime(metadata['series_last_observed']):
                print(f"🔎 Requested date exceeds known end date. Checking for updates...")
                update_metadata()

        # --- 3. CLAMP DATES ---
        if 'series_inception' in metadata and start_date:
            clamped_start = max(pd.to_datetime(start_date), pd.to_datetime(metadata['series_inception']))
            if pd.to_datetime(start_date) < clamped_start:
                start_date = clamped_start.strftime('%Y-%m-%d')
                print(f'⚠️ Adjusted start date to First Available Data: {start_date}')

        if 'series_last_observed' in metadata and end_date:
            clamped_end = min(pd.to_datetime(end_date), pd.to_datetime(metadata['series_last_observed']))
            if pd.to_datetime(end_date) > clamped_end:
                end_date = clamped_end.strftime('%Y-%m-%d')
                print(f'⚠️ FRED has no data past {end_date}. Adjusted request to match.')

        # --- 4. CHECK LOCAL CACHE ---
        cache_valid = False
        cache_start = None
        cache_end = None

        if os.path.exists(filepath):
            cache_valid = True

            if metadata_is_stale:
                cache_valid = False
                print(f"♻️ TTL expired. Forcing data and metadata refresh for {series_id}...")

            if cache_valid:
                if 'cache_start' in metadata and 'cache_end' in metadata:
                    cache_start = pd.to_datetime(metadata['cache_start'])
                    cache_end = pd.to_datetime(metadata['cache_end'])
                else:
                    try:
                        temp_df = pd.read_csv(filepath, index_col='DATE', parse_dates=True)
                        if not temp_df.empty:
                            cache_start = temp_df.index.min()
                            cache_end = temp_df.index.max()
                        else:
                            cache_valid = False
                    except Exception:
                        cache_valid = False

                if cache_valid and cache_start is not None:
                    if start_date and pd.to_datetime(start_date) < cache_start:
                        if len(pd.bdate_range(start_date, cache_start, inclusive='left')) > 0:
                            cache_valid = False

                    if end_date and pd.to_datetime(end_date) > cache_end:
                        freq_str = metadata.get('frequency', '')
                        if 'Annual' in freq_str:
                            cache_end_coverage = cache_end + pd.DateOffset(years=1) - pd.Timedelta(days=1)
                        elif 'Quarterly' in freq_str:
                            cache_end_coverage = cache_end + pd.DateOffset(months=3) - pd.Timedelta(days=1)
                        elif 'Monthly' in freq_str:
                            cache_end_coverage = cache_end + pd.DateOffset(months=1) - pd.Timedelta(days=1)
                        elif 'Weekly' in freq_str:
                            cache_end_coverage = cache_end + pd.Timedelta(days=6)
                        else:
                            cache_end_coverage = cache_end 
                        
                        if pd.to_datetime(end_date) > cache_end_coverage:
                            cache_valid = False

            if cache_valid:
                print(f"✅ Loaded {series_id} from local cache.")
                df = pd.read_csv(filepath, index_col='DATE', parse_dates=True)
                if start_date:
                    df = df[df.index >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[df.index <= pd.to_datetime(end_date)]
                return df
            else:
                print(f"♻️ Cache missing or insufficient bounds. Killing cache for {series_id}...")
                try:
                    os.remove(filepath)
                except OSError:
                    pass
                
                keys_removed = False
                if 'cache_start' in metadata:
                    del metadata['cache_start']
                    keys_removed = True
                if 'cache_end' in metadata:
                    del metadata['cache_end']
                    keys_removed = True
                
                if keys_removed:
                    with open(metadata_file, 'w') as f:
                        json.dump(metadata, f, indent=4)

        # --- 5. API FETCH ---
        print(f"☁️ Fetching fresh {series_id} observations...")
        if not metadata_updated_this_run and metadata_is_stale:
            if not update_metadata():
              return None

        try:
            if self.api_key is None:
                print("⚠️ No API key found. Defaulting to pandas_datareader...")
                df = web.DataReader(series_id, 'fred', start=start_date, end=end_date)
            else:
                url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={self.api_key}&file_type=json"
                if start_date: url += f"&observation_start={start_date}"
                if end_date: url += f"&observation_end={end_date}"

                safe_url = url.replace(self.api_key, "HIDDEN_KEY")
                print(f"📡 Sending URL to FRED: {safe_url}")

                data = self._make_api_request(url)

                if not data or 'observations' not in data:
                  print(f"❌ API Error: Could not retrieve observation data for {series_id}.")
                  return None

                df = pd.DataFrame(data['observations'])
                df['DATE'] = pd.to_datetime(df['date'])
                df[series_id] = pd.to_numeric(df['value'], errors='coerce')
                df = df.set_index('DATE')
                df = df[[series_id]]

            df.dropna(inplace=True)
            
            os.makedirs(self.cache_dir, exist_ok=True)            
 
            df.to_csv(filepath)
            
            if not df.empty:
                metadata['cache_start'] = df.index.min().strftime('%Y-%m-%d')
                metadata['cache_end'] = df.index.max().strftime('%Y-%m-%d')
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=4)
                    
            print(f"Success! Data saved to {filepath}.")
            return df

        except Exception as e:
            print(f"❌ An error occurred: {e}")
            return None       

