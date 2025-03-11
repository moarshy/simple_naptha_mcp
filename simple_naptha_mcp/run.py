import logging
import asyncio
import uvicorn
import threading
import time
import signal
import sys
from typing import Dict
from simple_naptha_mcp.schemas import InputSchema
from naptha_sdk.schemas import AgentRunInput
from simple_naptha_mcp.server import mcp_fetcher

logger = logging.getLogger(__name__)

# Server management
server_instance = None
server_thread = None
keep_running = True

def signal_handler(sig, frame):
    """Handle Ctrl+C to gracefully shut down the server"""
    global keep_running
    print("\nShutting down server...")
    keep_running = False
    stop_server()
    sys.exit(0)

def start_server(port=8000):
    """Start the MCP server in a separate thread"""
    global server_instance, server_thread
    
    def run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        starlette_app = mcp_fetcher.create_starlette_app(debug=True)
        logger.info(f"Starting MCP server on port {port}")
        config = uvicorn.Config(
            starlette_app, 
            host="0.0.0.0", 
            port=port, 
            log_level="info"
        )
        server_instance = uvicorn.Server(config)
        loop.run_until_complete(server_instance.serve())
    
    # Use a non-daemon thread so it can keep running
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = False  # This is important - non-daemon threads keep the program running
    server_thread.start()
    logger.info(f"Server thread started, available at http://localhost:{port}/sse")
    
    # Give the server a moment to start
    time.sleep(1)
    return True

def stop_server():
    """Stop the MCP server if it's running"""
    global server_instance, server_thread
    
    if server_instance:
        server_instance.should_exit = True
        logger.info("Server shutdown initiated")
    
    if server_thread and server_thread.is_alive():
        server_thread.join(timeout=5)
        logger.info("Server thread stopped")

def run(module_run: Dict, *args, **kwargs):
    """Main entry point for the agent"""
    try:
        # Parse the input
        module_run = AgentRunInput(**module_run)
        module_run.inputs = InputSchema(**module_run.inputs)
        logger.info(f"Received input: {module_run.inputs}")

        port = module_run.inputs.port
        
        # Start the MCP server if it's not already running
        if not server_thread or not server_thread.is_alive():
            success = start_server(port)
            if success:
                logger.info("MCP server started for this run")
            else:
                return {
                    "status": "error",
                    "message": f"Failed to start MCP server on port {port}"
                }
        
        return {
            "status": "success", 
            "message": f"MCP server started for this run on port {port}"
        }
    
    except Exception as e:
        logger.error(f"Error in run function: {e}", exc_info=True)
        # Make sure to stop the server if there's an error
        stop_server()
        raise

if __name__ == "__main__":
    import asyncio
    import os
    from naptha_sdk.configs import setup_module_deployment
    from naptha_sdk.client.naptha import Naptha
    
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    naptha = Naptha()

    deployment = asyncio.run(setup_module_deployment("agent", "simple_naptha_mcp/configs/deployment.json", node_url = os.getenv("NODE_URL")))

    input_params = {
        "port": 8001,
    }

    module_run = {
        "inputs": input_params,
        "deployment": deployment,
        "consumer_id": naptha.user.id,
        "signature": "ccccc"
    }

    response = run(module_run)
    print("Response: ", response)
    
    # Keep the main thread alive to prevent the program from exiting
    print("\nServer is running. Press Ctrl+C to stop.")
    try:
        # This loop keeps the main thread alive while the server runs
        while keep_running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server...")
        stop_server()