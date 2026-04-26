import subprocess, json, time
p = subprocess.Popen([".venv/bin/python", "mcp_server.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# 1. Initialize
req_init = {
  "jsonrpc": "2.0","id": 1,"method": "initialize",
  "params": {"protocolVersion": "2024-11-05","capabilities": {},"clientInfo": {"name": "test","version": "1.0"}}
}
p.stdin.write(json.dumps(req_init) + "\n")
p.stdin.flush()
print("INIT:", p.stdout.readline().strip())

# 2. Call Tool
req_call = {
  "jsonrpc": "2.0","id": 2,"method": "tools/call",
  "params": {
    "name": "get_alerts_near_location",
    "arguments": {"latitude": 33.4484,"longitude": -112.074,"radius_km": 50}
  }
}
p.stdin.write(json.dumps(req_call) + "\n")
p.stdin.flush()
print("TOOL:", p.stdout.readline().strip())

p.terminate()
