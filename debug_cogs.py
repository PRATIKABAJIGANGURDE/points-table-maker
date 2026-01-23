import sys
import traceback
import os
from dotenv import load_dotenv

# Mock discord and bot for import purposes if needed, 
# but mostly we just want to check syntax and import errors.

def check_cogs():
    print("🔍 Checking Cogs for errors...")
    cogs_dir = "cogs"
    
    # We need to ensure we can import from root
    sys.path.append(os.getcwd())

    cogs = [f for f in os.listdir(cogs_dir) if f.endswith('.py')]
    
    for cog in cogs:
        cog_name = f"cogs.{cog[:-3]}"
        print(f"\n👉 Attempting to import {cog_name}...")
        try:
            __import__(cog_name)
            print(f"✅ {cog_name} imported successfully.")
        except Exception:
            print(f"❌ Failed to import {cog_name}!")
            traceback.print_exc()

if __name__ == "__main__":
    check_cogs()
