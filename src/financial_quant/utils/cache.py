import os
import sys
import getpass
import glob
import shutil

def setup_cache_dir(folder_name: str, shared_env_var: str = None) -> str:
    """
    Determines the best location for the cache directory, handles Colab Drive mounting,
    and ensures the directory exists.
    """
    cache_dir = None

    if 'google.colab' in sys.modules:
        print("☁️ Colab environment detected. Attempting to mount Google Drive...")
        from google.colab import drive
        try:
            drive.mount('/content/drive')
            cache_dir = f'/content/drive/MyDrive/{folder_name.upper()}'
        except Exception as e:
            print(f"⚠️ Drive mount failed, defaulting to local cache: {e}")

    if not cache_dir:
        shared_env_path = os.environ.get(shared_env_var) if shared_env_var else None
        if shared_env_path:
            cache_dir = shared_env_path
        else:
            cache_dir = os.path.expanduser(f"~/{folder_name.lower()}")

    # Ensure the directory exists
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except PermissionError:
        print(f"⚠️ Warning: Lacking permission to create {cache_dir}. Cache may fail.")

    print(f"📂 Cache anchored at: {cache_dir}")
    return cache_dir

def cache_clear(cache_dir, symbol=None):
    """
    Clears the cache data inside the specified directory.
    If a symbol is provided, clears only files matching that symbol.
    """
    if symbol:
        search_pattern = os.path.join(cache_dir, f"*{symbol}*")
        files_to_remove = glob.glob(search_pattern)
        
        if not files_to_remove:
            print(f"ℹ️ No cached files found for symbol: {symbol}")
            return

        for file_path in files_to_remove:
            try:
                os.remove(file_path)
                print(f"🗑️ Cleared specific cache file: {file_path}")
            except Exception as e:
                print(f"⚠️ Error removing {file_path}: {e}")
    else:
        # Clear the entire cache directory
        for filename in os.listdir(cache_dir):
            file_path = os.path.join(cache_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"⚠️ Error removing {file_path}: {e}")
        
        print(f"🧹 Entire cache cleared successfully from {cache_dir}.")
