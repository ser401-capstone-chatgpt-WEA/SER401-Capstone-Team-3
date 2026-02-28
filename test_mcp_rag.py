import asyncio
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

if __name__ == "__main__":
    asyncio.run(test_rag_tool())
