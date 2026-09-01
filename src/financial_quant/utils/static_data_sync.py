"""
=============================================================================
STATIC DATA SYNC UTILITY
=============================================================================
Environment-aware utility for converting local CSVs to Parquet format, validating 
them interactively, and pushing them directly to a GitHub data repository. 

🔒 PREREQUISITE: 
This script requires a GitHub Personal Access Token (PAT) named 'GITHUB_TOKEN'.
  - In Google Colab: Add it to your Colab Secrets (the key icon).
  - On Local Machine: Export it as an OS environment variable.
  - Fallback: The script will securely prompt you for it during execution.
=============================================================================
"""

import os
import sys
import shutil
import pandas as pd
import subprocess
import getpass
from pathlib import Path

def _convert_validate_approve(csv_path):
    """
    Internal function: Converts CSV to a local temp.parquet, 
    displays the head, gets user approval, and returns True if kept.
    """
    temp_file = "temp.parquet"
    
    try:
        # Convert to local temp file
        pd.read_csv(csv_path).to_parquet(temp_file, engine='pyarrow')
        
        # Read back and display for validation
        df = pd.read_parquet(temp_file)
        print(f"\n{'='*50}")
        print(f"📄 File: {csv_path.name} | Shape: {df.shape}")
        print(f"{'='*50}")
        print(df.head())
        print(f"{'='*50}\n")
        
        # Interactive human-in-the-loop approval
        while True:
            choice = input(f"Approve {csv_path.name} for upload? (y/n): ").strip().lower()
            if choice in ['y', 'yes']:
                print("✅ Approved.")
                return True
            elif choice in ['n', 'no']:
                print("❌ Rejected. Dropping file...")
                os.remove(temp_file)
                return False
                
    except Exception as e:
        print(f"⚠️ Error processing {csv_path.name}: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def process_and_push(input_csv_folder, repo_name, target_repo_folder):
    """
    Scans a folder for CSVs, converts them to Parquet with user validation, 
    and securely pushes approved files to a target GitHub repository.
    
    Authentication:
        - Colab: Looks for 'GITHUB_TOKEN' in Colab Secrets.
        - Local: Looks for 'GITHUB_TOKEN' in OS environment variables.
        - Fallback: Prompts the user via secure hidden text input.
    
    Args:
        input_csv_folder (str): Local path containing raw CSVs.
        repo_name (str): GitHub repository (e.g., 'PatrickJHess/static_data_repo').
        target_repo_folder (str): Folder inside the repo to store the Parquets (e.g., 'data/2026').
    """
    repo_dir = "temp_repo_clone"
    approved_count = 0
    original_dir = os.getcwd()
    
    # --- 1. Authentication Cascade ---
    gh_token = None
    
    # Check Colab Secrets first
    if 'google.colab' in sys.modules:
        from google.colab import userdata
        try:
            gh_token = userdata.get('GITHUB_TOKEN')
        except userdata.SecretNotFoundError:
            pass 
            
    # Check Local Environment Variables second
    if not gh_token:
        gh_token = os.environ.get('GITHUB_TOKEN')
        
    # Fallback to manual secure input
    if not gh_token:
        print("\n🔑 GitHub Token not found in environment or Colab secrets.")
        gh_token = getpass.getpass("Paste your GitHub PAT (input will be hidden): ").strip()
        if gh_token:
            os.environ['GITHUB_TOKEN'] = gh_token
            
    if not gh_token:
        print("❌ ERROR: A GitHub token is required to proceed.")
        return

    repo_url = f"https://{gh_token}@github.com/{repo_name}.git"

    # --- 2. Setup Ephemeral Workspace ---
    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)
        
    try:
        print(f"\nCloning {repo_name} into temporary workspace...")
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, repo_dir], 
            check=True, capture_output=True
        )
        
        target_path = Path(repo_dir) / target_repo_folder
        os.makedirs(target_path, exist_ok=True)
        
        # --- 3. Process CSVs ---
        csv_files = list(Path(input_csv_folder).rglob("*.csv"))
        if not csv_files:
            print(f"⚠️ No CSV files found in {input_csv_folder}.")
            return
            
        for csv_file in csv_files:
            is_approved = _convert_validate_approve(csv_file)
            
            if is_approved:
                # Sanitize filename: replace colons with underscores for OS/Git safety
                clean_name = csv_file.with_suffix('.parquet').name.replace(':', '_')
                final_dest = target_path / clean_name
                if final_dest.exists():
                    existing_df = pd.read_parquet(final_dest)
                    new_df = pd.read_parquet("temp.parquet")
                    
                    # Compare actual data, ignoring file metadata/timestamps
                    if existing_df.equals(new_df):
                        print(f"⏩ Data for {clean_name} is unchanged. Skipping update.")
                        os.remove("temp.parquet")
                        continue # Skip to the next CSV
                
                shutil.move("temp.parquet", final_dest)
                approved_count += 1
                
        # --- 4. Push if approved ---
        if approved_count > 0:
            print(f"\n{approved_count} files approved. Preparing Git push...")
            os.chdir(repo_dir)
            
            # Git requires an identity in headless/Colab environments
            if 'google.colab' in sys.modules:
                subprocess.run(["git", "config", "user.email", "bot@colab.com"])
                subprocess.run(["git", "config", "user.name", "Colab Bot"])
                
            subprocess.run(["git", "add", "."], check=True)
            
            # Check if files are actually different from what is on GitHub
            status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            
            if status.stdout.strip():
                subprocess.run(["git", "commit", "-m", "Auto-update: CSV to Parquet batch upload"], check=True)
                subprocess.run(["git", "push"], check=True)
                print("🎉 Successfully pushed updates to GitHub.")
            else:
                print("🤷‍♂️ No updates needed. The approved files are identical to the repository.")
        else:
            print("\nNo files were approved. Skipping push.")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Git command failed: {e}")
    finally:
        # --- 5. Cleanup ---
        os.chdir(original_dir)
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir)
            print("🧹 Temporary workspace cleaned up.")

if __name__ == "__main__":
    print("====================================================================")
    print("STATIC DATA SYNC UTILITY")
    print("=====================================================================")
    print("Import this module to use:")
    print("  process_and_push(input_csv_folder, repo_name, target_repo_folder)")
    print("\n⚠️ Note:  BEFORE RUNNING: Ensure 'GITHUB_TOKEN' is available")
    print("  or configured in Colab Secrets or your local environment variables.")
    print("======================================================================")
