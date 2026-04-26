import asyncio
import json
import time
import os
import sys

# Color configurations
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

BANNER = f"""{Colors.OKBLUE}{Colors.BOLD}
===========================================================
      PBS WARN EMERGENCY ALERTS - SYSTEM DEMO
===========================================================
{Colors.ENDC}"""

def print_help():
    print(f"\n{Colors.WARNING}Available Commands:{Colors.ENDC}")
    print(f"  {Colors.OKCYAN}/query <question>{Colors.ENDC}   - Ask the RAG system a natural language query.")
    print(f"  {Colors.OKCYAN}/status{Colors.ENDC}             - Check system emergency status (latest alerts).")
    print(f"  {Colors.OKCYAN}/region <state>{Colors.ENDC}     - Get alert summary for a specific state (e.g. Arizona).")
    print(f"  {Colors.OKCYAN}/quit{Colors.ENDC}               - Exit the demo.")
    print("\nJust typing a message will default to the a /query command.\n")

async def run_demo():
    print(BANNER)
    print(f"{Colors.OKCYAN}Initializing RAG components and Vector DB... Please wait.{Colors.ENDC}")
    
    start_time = time.time()
    try:
        from mcp_server import call_tool, get_rag_components
        get_rag_components() # Pre-load models
    except Exception as e:
        print(f"{Colors.FAIL}Failed to initialize system: {e}{Colors.ENDC}")
        sys.exit(1)
        
    print(f"{Colors.OKGREEN}Initialization complete in {time.time()-start_time:.2f} seconds.{Colors.ENDC}")
    print_help()

    while True:
        try:
            cmd = input(f"{Colors.BOLD}Emergency Query > {Colors.ENDC}").strip()
            if not cmd:
                continue

            if cmd.lower() in ['/quit', '/exit']:
                print(f"{Colors.OKCYAN}Shutting down demo...{Colors.ENDC}")
                break
                
            elif cmd.lower() == '/help':
                print_help()
                continue
                
            elif cmd.lower().startswith('/region'):
                parts = cmd.split(' ', 1)
                region = parts[1] if len(parts) > 1 else 'Arizona'
                await handle_region(region, call_tool)
                
            elif cmd.lower() == '/status':
                await handle_status(call_tool)
                
            elif cmd.lower().startswith('/query'):
                parts = cmd.split(' ', 1)
                if len(parts) > 1:
                    await handle_query(parts[1], call_tool)
                else:
                    print(f"{Colors.WARNING}Please specify a query.{Colors.ENDC}")
            else:
                # Default to query
                await handle_query(cmd, call_tool)

        except KeyboardInterrupt:
            print(f"\n{Colors.OKCYAN}Shutting down demo...{Colors.ENDC}")
            break
        except Exception as e:
            print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")

async def handle_query(query: str, call_tool):
    print(f"\n{Colors.HEADER}--- Processing Request via RAG Pipeline ---{Colors.ENDC}")
    args = {"query": query}
    
    t0 = time.time()
    try:
        from mcp_server import call_tool
        result = await call_tool("ask_alert_knowledge_base", args)
        t1 = time.time()
        
        if result and len(result) > 0:
            content = result[0].text
            print(f"{Colors.OKGREEN}Generated response in {t1-t0:.2f}s:{Colors.ENDC}\n")
            print(content)
        else:
            print(f"{Colors.FAIL}No response was returned.{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}Pipeline Failed: {e}{Colors.ENDC}")
    print(f"{Colors.HEADER}-------------------------------------------{Colors.ENDC}\n")


async def handle_region(region: str, call_tool):
    print(f"\n{Colors.HEADER}--- Fetching Alert Summary for {region} ---{Colors.ENDC}")
    args = {"region": region}
    try:
        t0 = time.time()
        result = await call_tool("get_alert_summary_for_region", args)
        t1 = time.time()
        
        if result and len(result) > 0:
            data = json.loads(result[0].text)
            print(f"{Colors.OKGREEN}Fetched in {t1-t0:.2f}s:{Colors.ENDC}\n")
            print(json.dumps(data, indent=2))
        else:
            print(f"{Colors.FAIL}No response was returned.{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}Tool Failed: {e}{Colors.ENDC}")
    print(f"{Colors.HEADER}-------------------------------------------{Colors.ENDC}\n")


async def handle_status(call_tool):
    print(f"\n{Colors.HEADER}--- Checking System Emergency Status ---{Colors.ENDC}")
    try:
        t0 = time.time()
        result = await call_tool("check_emergency_status", {})
        t1 = time.time()
        
        if result and len(result) > 0:
            data = json.loads(result[0].text)
            print(f"{Colors.OKGREEN}Fetched in {t1-t0:.2f}s:{Colors.ENDC}\n")
            print(json.dumps(data, indent=2))
        else:
            print(f"{Colors.FAIL}No response was returned.{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}Tool Failed: {e}{Colors.ENDC}")
    print(f"{Colors.HEADER}-------------------------------------------{Colors.ENDC}\n")

if __name__ == "__main__":
    if not os.getenv("GEMINI_API_KEY"):
        print(f"{Colors.FAIL}Error: GEMINI_API_KEY environment variable is not set.{Colors.ENDC}")
        sys.exit(1)
    asyncio.run(run_demo())
