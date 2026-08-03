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


def cache_inventory(cache_dir: str, symbol: str = ''):
    """
    Scans the cache directory and prints a helpful inventory of available files.
    Only inventories files with a .csv suffix that start with the provided symbol.
    """
    if not os.path.exists(cache_dir):
        print(f"ℹ️ Cache directory does not exist: {cache_dir}")
        return []

    # Modified: filter for .csv files AND files that start with the symbol string
    files = [
        f for f in os.listdir(cache_dir) 
        if os.path.isfile(os.path.join(cache_dir, f)) 
        and f.endswith('.csv') 
        and f.startswith(symbol)
    ]
    
    if not files:
        print("📂 The cache directory is currently empty or no files match your criteria.")
        return []

    print(f"📂 Found {len(files)} matching .csv files in cache:")
    for f in files[:15]:  # Limit output to prevent console spam
        print(f"  - {f}")
    
    if len(files) > 15:
        print(f"  ... plus {len(files) - 15} more files.")
        
    return files


def cache_clear(cache_dir: str, symbol: str = None, force: bool = False):
    """
    Clears the cache data inside the specified directory.
    If a symbol is provided and multiple files exist, allows multi-selection.
    Requires explicit 'yes' confirmation unless force=True.
    """
    if not os.path.exists(cache_dir):
        print(f"⚠️ Cache directory not found: {cache_dir}")
        return

    if symbol:
        search_pattern = os.path.join(cache_dir, f"{symbol}_*")
        files_to_remove = glob.glob(search_pattern)
        
        if not files_to_remove:
            print(f"ℹ️ No cached files found for symbol: '{symbol}'")
            print("---")
            # Modified: Now passes the symbol into cache_inventory to show relevant .csv files
            cache_inventory(cache_dir, symbol) 
            return

        selected_files = files_to_remove

        # Step 1: Multi-file selection menu
        if len(files_to_remove) > 1 and not force:
            print(f"⚠️ Multiple files found for symbol '{symbol}':")
            for i, file_path in enumerate(files_to_remove, 1):
                print(f"  [{i}] {os.path.basename(file_path)}")
            
            print("  [all] Delete ALL of the above")
            print("  [0] Cancel")
            
            choice = input("\nEnter file numbers to delete (e.g., '1', '1, 3'), 'all', or '0': ").strip().lower()
            
            if choice in ['0', '']:
                print("🚫 Operation cancelled.")
                return
            elif choice != 'all':
                selected_files = []
                try:
                    # Parse comma-separated inputs and use set() to prevent duplicate selections
                    indices = set([int(x.strip()) for x in choice.split(',')])
                    for idx in indices:
                        if 1 <= idx <= len(files_to_remove):
                            selected_files.append(files_to_remove[idx - 1])
                        else:
                            print(f"⚠️ Invalid choice '{idx}' ignored.")
                except ValueError:
                    print("🚫 Invalid input format. Operation cancelled.")
                    return

            if not selected_files:
                print("🚫 No valid files selected. Operation cancelled.")
                return

        # Step 2: Final strict confirmation (for both single and multiple files)
        if not force:
            print("\n⚠️ You are about to delete the following file(s):")
            for f in selected_files:
                print(f"  - {os.path.basename(f)}")
            
            confirm = input("\nType 'yes' to confirm (press Enter or anything else to cancel): ").strip().lower()
            if confirm != 'yes':
                print("🚫 Operation cancelled. The cache was not modified.")
                return

        # Step 3: Execute the deletion
        for file_path in selected_files:
            try:
                os.remove(file_path)
                print(f"🗑️ Cleared: {os.path.basename(file_path)}")
            except Exception as e:
                print(f"⚠️ Error removing {os.path.basename(file_path)}: {e}")
                
    else:
        # Warning and Confirmation for clearing the ENTIRE cache
        if not force:
            print(f"⚠️ WARNING: You are about to delete ALL cached data in:")
            print(f"   {cache_dir}")
            confirm = input("Type 'yes' to proceed (press Enter or anything else to cancel): ").strip().lower()
            
            if confirm != 'yes':
                print("🚫 Operation cancelled. The cache was not modified.")
                return

        deleted_count = 0
        for filename in os.listdir(cache_dir):
            file_path = os.path.join(cache_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                deleted_count += 1
            except Exception as e:
                print(f"⚠️ Error removing {file_path}: {e}")
        
        print(f"🧹 Entire cache cleared successfully ({deleted_count} items removed).")
