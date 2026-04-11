import asyncio
import json
import os
from mcp_server import call_tool, get_rag_components

async def test_rag_tool():
    print("Testing 'ask_alert_knowledge_base' tool...")
    
    # Verify environment
    if not os.getenv("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY not found in environment.")
        return

    # Mock arguments
    args = {"query": "Summarize the emergency alerts related to shelters."}
    
    try:
        # Call the tool directly
        result = await call_tool("ask_alert_knowledge_base", args)
        
        # Check output
        if result and len(result) > 0:
            content = result[0].text
            print("\nTool Output:")
            print(content)
            
            if "success" in content and "true" in content.lower():
                print("\nTEST PASSED: RAG tool returned success.")
            else:
                print("\nTEST FAILED: RAG tool did not return success.")
        else:
            print("\nTEST FAILED: No output from tool.")
            
        print("\nTesting OpenAI MCP Error Schema Compatibility...")
        bad_args = {} # Missing required 'latitude' & 'longitude'
        result_err = await call_tool("check_emergency_status", bad_args)
        if result_err and len(result_err) > 0:
            err_content = result_err[0].text
            print("\nError Tool Output:")
            print(err_content)
            if "success\": false" in err_content.lower() and "error" in err_content.lower():
                print("\nTEST PASSED: Gracefully handled bad inputs with ChatGPT compatibility schema.")
            else:
                print("\nTEST FAILED: Did not return standard error schema.")

    except Exception as e:
        print(f"\nTEST FAILED: Exception occurred: {e}")


async def test_region_search():
    """Test get_alert_summary_for_region with various region inputs."""
    print("\n" + "="*60)
    print("Testing 'get_alert_summary_for_region' tool...")
    
    test_cases = [
        {"region": "Arizona"},
        {"region": "phoenix"},
        {"region": "CA"},
    ]
    
    for args in test_cases:
        try:
            result = await call_tool("get_alert_summary_for_region", args)
            if result and len(result) > 0:
                data = json.loads(result[0].text)
                region = args["region"]
                count = data.get("count", "?")
                print(f"  Region '{region}': {count} alerts found — {'PASS' if data.get('success') else 'FAIL'}")
            else:
                print(f"  Region '{args['region']}': FAIL — no output")
        except Exception as e:
            print(f"  Region '{args['region']}': FAIL — {e}")


async def test_unknown_tool():
    """Test that an unknown tool name returns a structured error."""
    print("\n" + "="*60)
    print("Testing unknown tool name error handling...")
    
    try:
        result = await call_tool("nonexistent_tool", {})
        if result and len(result) > 0:
            data = json.loads(result[0].text)
            if data.get("success") is False and "error" in data:
                print("  TEST PASSED: Unknown tool returned structured error JSON.")
            else:
                print("  TEST FAILED: Unexpected response format.")
        else:
            print("  TEST FAILED: No output.")
    except ValueError:
        print("  TEST PASSED: Unknown tool raised ValueError as expected.")
    except Exception as e:
        print(f"  TEST FAILED: Unexpected exception: {e}")


if __name__ == "__main__":
    asyncio.run(test_rag_tool())
    asyncio.run(test_region_search())
    asyncio.run(test_unknown_tool())
