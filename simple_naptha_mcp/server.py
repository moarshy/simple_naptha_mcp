import httpx
import mcp.types as types
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.requests import Request
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
import logging

logger = logging.getLogger(__name__)

class MCPWebsiteFetcher:
    def __init__(self):
        self.app = Server("mcp-website-fetcher")
        self.setup_tools()
        
    async def fetch_website(self, url: str) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        headers = {
            "User-Agent": "MCP Test Server (github.com/modelcontextprotocol/python-sdk)"
        }
        async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            return [types.TextContent(type="text", text=response.text)]

    async def echo_message(self, message: str) -> list[types.TextContent]:
        return [types.TextContent(type="text", text=message)]

    async def say_hello(self, name: str = "World") -> list[types.TextContent]:
        return [types.TextContent(type="text", text=f"Hello, {name}!")]
    
    def setup_tools(self):
        @self.app.call_tool()
        async def fetch_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            if name == "fetch":
                if "url" not in arguments:
                    raise ValueError("Missing required argument 'url'")
                return await self.fetch_website(arguments["url"])
            elif name == "echo":
                if "message" not in arguments:
                    raise ValueError("Missing required argument 'message'")
                return await self.echo_message(arguments["message"])
            elif name == "hello":
                name_arg = arguments.get("name", "World")
                return await self.say_hello(name_arg)
            else:
                raise ValueError(f"Unknown tool: {name}")

        @self.app.list_tools()
        async def list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name="fetch",
                    description="Fetches a website and returns its content",
                    inputSchema={
                        "type": "object",
                        "required": ["url"],
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to fetch",
                            }
                        },
                    },
                ),
                types.Tool(
                    name="echo",
                    description="Returns the provided message",
                    inputSchema={
                        "type": "object",
                        "required": ["message"],
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "Message to echo back",
                            }
                        },
                    },
                ),
                types.Tool(
                    name="hello",
                    description="Returns a greeting message",
                    inputSchema={
                        "type": "object",
                        "required": [],
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Name to greet (defaults to 'World')",
                            }
                        },
                    },
                )
            ]
    
    def create_starlette_app(self, debug: bool = False) -> Starlette:
        """Create a Starlette application that can serve the provided mcp server with SSE."""
        sse = SseServerTransport("/messages/")

        async def handle_sse(request: Request) -> None:
            async with sse.connect_sse(
                    request.scope,
                    request.receive,
                    request._send,  # noqa: SLF001
            ) as (read_stream, write_stream):
                await self.app.run(
                    read_stream,
                    write_stream,
                    self.app.create_initialization_options(),
                )

        return Starlette(
            debug=debug,
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )

# Create a singleton instance to be imported by run.py
mcp_fetcher = MCPWebsiteFetcher()