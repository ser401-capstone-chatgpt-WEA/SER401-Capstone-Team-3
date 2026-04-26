import time
import sys
import os

LOG_FILE = "pbs_warn_scraper.log"

def start_dashboard():
    # Clear terminal
    print("\033[2J\033[H", end="")
    
    print("\033[96m\033[1m" + "="*70 + "\033[0m")
    print("\033[96m\033[1m                 PBS WARN RAG + MCP LIVE BACKEND                 \033[0m")
    print("\033[96m\033[1m" + "="*70 + "\033[0m")
    print("\033[93m\033[1m Listening for JSON-RPC Tool Invocations from Claude Desktop...\033[0m\n")

    if not os.path.exists(LOG_FILE):
        print(f"\033[91m[ERROR]\033[0m Log file '{LOG_FILE}' not found.")
        print("Ensure you are running this in the root of your SER401-Capstone directory.")
        return

    try:
        with open(LOG_FILE, "r") as f:
            # Go directly to the end of the file and only watch for NEW events
            f.seek(0, 2)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                
                line = line.strip()
                
                # Dynamic terminal color formatting based on system components
                if "[MCP]" in line:
                    print(f"\033[95m\033[1m[MCP SERVER]\033[0m \033[97m{line}\033[0m")
                elif "Retrieved" in line or "threshold" in line:
                    print(f"\033[92m\033[1m[RAG DATABASE]\033[0m \033[92m{line}\033[0m")
                elif "Generated" in line or "LLM" in line:
                    print(f"\033[94m\033[1m[RAG GEMINI LLM]\033[0m \033[96m{line}\033[0m")
                elif "Error" in line or "Exception" in line or "Failed" in line:
                    print(f"\033[91m\033[1m[ERROR]\033[0m \033[91m{line}\033[0m")
                else:
                    print(f"\033[97m[SYSTEM]\033[0m \033[97m{line}\033[0m")
                    
    except KeyboardInterrupt:
        print("\n\033[96m[SYSTEM] Shutting down live dashboard...\033[0m")
        sys.exit(0)

if __name__ == "__main__":
    start_dashboard()
# IC6 Fix - Apr 18
