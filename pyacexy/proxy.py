"""Main proxy server implementation"""
import argparse
import asyncio
import logging
import os
from typing import Optional
from urllib.parse import parse_qs, urlparse

from aiohttp import web, ClientSession
from .aceid import AceIDManager
from .copier import StreamCopier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AcexyProxy:
    """AceStream HTTP Proxy Server"""
    
    def __init__(
        self,
        acestream_host: str = "localhost",
        acestream_port: int = 6878,
        scheme: str = "http",
        buffer_size: int = 4 * 1024 * 1024,
        m3u8_mode: bool = False,
    ):
        self.acestream_host = acestream_host
        self.acestream_port = acestream_port
        self.scheme = scheme
        self.buffer_size = buffer_size
        self.m3u8_mode = m3u8_mode
        
        self.pid_manager = AceIDManager()
        self.streams = {}
        self.session: Optional[ClientSession] = None
    
    async def handle_getstream(self, request: web.Request) -> web.StreamResponse:
        """Handle /ace/getstream endpoint"""
        # Get stream ID from query parameters
        stream_id = request.query.get('id')
        if not stream_id:
            return web.Response(status=400, text="Missing stream ID")
        
        # Generate unique PID for this client
        client_id = f"{request.remote}:{id(request)}"
        pid = self.pid_manager.generate_pid(stream_id, client_id)
        
        logger.info(f"Client {client_id} requesting stream {stream_id} with PID {pid}")
        
        # Build AceStream middleware URL
        acestream_url = (
            f"{self.scheme}://{self.acestream_host}:{self.acestream_port}"
            f"/ace/getstream?id={stream_id}&pid={pid}"
        )
        
        # Add additional query parameters if provided
        for key, value in request.query.items():
            if key != 'id':
                acestream_url += f"&{key}={value}"
        
        # Create response
        response = web.StreamResponse()
        response.content_type = 'video/mp2t' if not self.m3u8_mode else 'application/x-mpegURL'
        await response.prepare(request)
        
        try:
            # Connect to AceStream middleware
            async with self.session.get(acestream_url) as ace_response:
                if ace_response.status != 200:
                    logger.error(f"AceStream returned status {ace_response.status}")
                    return web.Response(status=502, text="AceStream error")
                
                # Stream data to client
                async for chunk in ace_response.content.iter_chunked(8192):
                    await response.write(chunk)
                    
        except Exception as e:
            logger.error(f"Error streaming: {e}")
        finally:
            self.pid_manager.remove_pid(stream_id, pid)
            await response.write_eof()
        
        return response
    
    async def start_server(self, host: str = "0.0.0.0", port: int = 8080):
        """Start the proxy server"""
        self.session = ClientSession()
        
        app = web.Application()
        app.router.add_get('/ace/getstream', self.handle_getstream)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, host, port)
        await site.start()
        
        logger.info(f"PyAcexy proxy started on {host}:{port}")
        logger.info(f"Connecting to AceStream at {self.scheme}://{self.acestream_host}:{self.acestream_port}")
        
        # Keep running
        try:
            await asyncio.Event().wait()
        finally:
            await self.session.close()
            await runner.cleanup()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="PyAcexy - AceStream HTTP Proxy")
    parser.add_argument(
        "--host",
        default=os.getenv("ACEXY_HOST", "localhost"),
        help="AceStream middleware host"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ACEXY_PORT", "6878")),
        help="AceStream middleware port"
    )
    parser.add_argument(
        "--listen-addr",
        default=os.getenv("ACEXY_LISTEN_ADDR", ":8080"),
        help="Address to listen on (format: [host]:port)"
    )
    parser.add_argument(
        "--scheme",
        default=os.getenv("ACEXY_SCHEME", "http"),
        help="AceStream middleware scheme (http/https)"
    )
    parser.add_argument(
        "--buffer-size",
        type=int,
        default=int(os.getenv("ACEXY_BUFFER_SIZE", str(4 * 1024 * 1024))),
        help="Buffer size in bytes"
    )
    parser.add_argument(
        "--m3u8",
        action="store_true",
        default=os.getenv("ACEXY_M3U8", "").lower() == "true",
        help="Enable M3U8/HLS mode"
    )
    
    args = parser.parse_args()
    
    # Parse listen address
    listen_parts = args.listen_addr.split(":")
    listen_host = listen_parts[0] if listen_parts[0] else "0.0.0.0"
    listen_port = int(listen_parts[1]) if len(listen_parts) > 1 else 8080
    
    # Create and start proxy
    proxy = AcexyProxy(
        acestream_host=args.host,
        acestream_port=args.port,
        scheme=args.scheme,
        buffer_size=args.buffer_size,
        m3u8_mode=args.m3u8,
    )
    
    try:
        asyncio.run(proxy.start_server(listen_host, listen_port))
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
