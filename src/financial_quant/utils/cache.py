import os
import sys
import getpass

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
