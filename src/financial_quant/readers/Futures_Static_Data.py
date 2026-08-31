import sys
import requests
import pandas as pd
from io import BytesIO
from pathlib import Path

# 1. Define repo configuration
GITHUB_RAW_BASE_URL = "https://raw.githubusercontent.com/PatrickJHess/Static_Data_Repo/main/Futures"

# 2. Environment-Aware Cache Routing with Google Drive
if 'google.colab' in sys.modules:
    from google.colab import drive
    # Mount Google Drive (will prompt for authorization if not already mounted)
    drive.mount('/content/drive')
    # Route cache to persistent Google Drive folder
    DEFAULT_CACHE_DIR = Path("/content/drive/MyDrive/Futures_Static")
else:
    # Use standard local directory for Jupyter/VSCode
    DEFAULT_CACHE_DIR = Path.cwd() / "cache" / "Futures_Static"

def static_futures_data(file_name, cache_dir=DEFAULT_CACHE_DIR):
    # 3. Standardize Parquet Filename 
    filename = f"{file_name}.parquet"
        # Ensure local cache folder exists
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    file_path = cache_path / filename

    df = None

    # 4. Tier 1: Check Local/Drive Cache First
    if file_path.exists():
        print(f"Loading Parquet data from local cache: {filename}")
        df = pd.read_parquet(file_path)
        
    # 5. Tier 2: Fetch from GitHub Static Repo if not in cache
    else:
        print(f"Fetching Parquet data from GitHub: {filename}")
        github_url = f"{GITHUB_RAW_BASE_URL}/{filename}"
        try:
            # Fetch raw binary data from GitHub
            response = requests.get(github_url, timeout=10)
            response.raise_for_status()
            
            # Read bytes directly into Pandas
            df = pd.read_parquet(BytesIO(response.content))
            
            # Save a copy to Google Drive/Local cache to bypass GitHub next time
            df.to_parquet(file_path, index=False)
            df = df.set_index('Date')
        except requests.exceptions.HTTPError as e:
            if response.status_code == 404:
                return f"Data for {price_date} not found in GitHub Repo: {filename}", None, None
            return f"HTTP Error fetching from GitHub: {e}", None, None
        except Exception as e:
            return f"Error loading Parquet data: {e}", None, None
    
    return df
