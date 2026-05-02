import asyncio
import json
import logging
import uuid
import sys
from pathlib import Path

# Add project root to sys.path so we can import backend
sys.path.append(str(Path(__file__).parent.parent))

import backend.graph.graph as graph_module
from backend.job_manager import create_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("demo_api_test")

async def run_demo():
    log.info("Starting Demo API Test...")
    
    # Initialize the graph
    await graph_module.init_graph()
    
    target_url = sys.argv[1] if len(sys.argv) > 1 else "https://jsonplaceholder.typicode.com"
    
    job_id, initial_state = create_job(
        target_url=target_url,
        language="python",
        page_content="",
        page_links=[]
    )
    
    log.info(f"Created Job: {job_id}")
    log.info("Running graph. This will hit the real API and LangGraph...")
    
    try:
        config = {"configurable": {"thread_id": job_id}}
        
        # We use astream to stream the state updates node by node
        async for output in graph_module.compiled_graph.astream(initial_state, config):
            for node, state_update in output.items():
                log.info(f"--- Node '{node}' completed ---")
                if "messages" in state_update and state_update["messages"]:
                    last_msg = state_update["messages"][-1]
                    log.info(f"Message from {node}: {last_msg.content}")
                
        # Final state
        final_state = await graph_module.compiled_graph.aget_state(config)
        log.info("=== Final SDK Files ===")
        files = final_state.values.get("sdk_files", {})
        if files:
            for file_path, content in files.items():
                log.info(f"File: {file_path} ({len(content)} chars)")
        else:
            log.warning("No SDK files generated!")
            
    except Exception as e:
        log.error(f"Error during graph execution: {e}", exc_info=True)
    finally:
        await graph_module.teardown_graph()
        log.info("Teardown complete.")

if __name__ == "__main__":
    asyncio.run(run_demo())
