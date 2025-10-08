"""Main proxy server implementation"""
import argparse
import asyncio
import json
import logging
import os
import uuid
from typing import Optional, Dict
from urllib.parse import parse_qs, urlparse, urlencode

import aiohttp
from aiohttp import web, ClientSession
from .aceid import AceIDManager
from .copier import StreamCopier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AceStream:
    """AceStream session information"""
    
    def __init__(self, playback_url: str, stat_url: str, command_url: str, stream_id: str):
        self.playback_url = playback_url
        self.stat_url = stat_url
        self.command_url = command_url
        self.stream_id = stream_id


class OngoingStream:
    """Represents an ongoing stream with multiple clients"""
    
    def __init__(self, stream_id: str, acestream: AceStream):
        self.stream_id = stream_id
        self.acestream = acestream
        self.clients = set()
        self.copier: Optional[StreamCopier] = None
        self.task: Optional[asyncio.Task] = None
        self.lock = asyncio.Lock()
        self.done = asyncio.Event()
        self.started = asyncio.Event()
        self.first_chunk = asyncio.Event()
        self.client_last_write = {}  # Track last successful write time per client
        

class AcexyProxy:
    """AceStream HTTP Proxy Server"""
    
    def __init__(
        self,
        acestream_host: str = "localhost",
        acestream_port: int = 6878,
        scheme: str = "http",
        buffer_size: int = 4 * 1024 * 1024,
        m3u8_mode: bool = False,
        empty_timeout: float = 60.0,
        no_response_timeout: float = 1.0,
        stream_timeout: float = 60.0,
    ):
        self.acestream_host = acestream_host
        self.acestream_port = acestream_port
        self.scheme = scheme
        self.buffer_size = buffer_size
        self.m3u8_mode = m3u8_mode
        self.empty_timeout = empty_timeout
        self.no_response_timeout = no_response_timeout
        self.stream_timeout = stream_timeout
        self.endpoint = "/ace/manifest.m3u8" if m3u8_mode else "/ace/getstream"
        
        self.pid_manager = AceIDManager()
        self.streams: Dict[str, OngoingStream] = {}
        self.session: Optional[ClientSession] = None
        self.streams_lock = asyncio.Lock()
    
    async def _fetch_stream_info(self, stream_id: str, infohash: str, extra_params: dict) -> AceStream:
        """Fetch stream information from AceStream middleware"""
        # Generate temporary PID for this request
        temp_pid = str(uuid.uuid4())
        
        # Build request URL
        url = f"{self.scheme}://{self.acestream_host}:{self.acestream_port}{self.endpoint}"
        
        # Build query parameters
        params = extra_params.copy()
        params['format'] = 'json'
        params['pid'] = temp_pid
        
        if stream_id:
            params['id'] = stream_id
        elif infohash:
            params['infohash'] = infohash
        else:
            raise ValueError("Either id or infohash must be provided")
        
        logger.debug(f"Fetching stream info: {url}?{urlencode(params)}")
        
        # Set timeout for this request
        timeout = aiohttp.ClientTimeout(total=self.no_response_timeout)
        
        async with self.session.get(url, params=params, timeout=timeout) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"AceStream middleware returned {response.status}: {error_text}")
            
            data = await response.json()
            
            if 'error' in data and data['error']:
                raise Exception(f"AceStream error: {data['error']}")
            
            if 'response' not in data:
                raise Exception("Invalid response from AceStream middleware")
            
            resp = data['response']
            
            return AceStream(
                playback_url=resp['playback_url'],
                stat_url=resp.get('stat_url', ''),
                command_url=resp['command_url'],
                stream_id=stream_id or infohash
            )
    
    async def _close_stream(self, acestream: AceStream):
        """Close stream on AceStream middleware"""
        try:
            url = f"{acestream.command_url}?method=stop"
            logger.debug(f"Closing stream: {url}")
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'error' in data and data['error']:
                        logger.warning(f"Error closing stream: {data['error']}")
                else:
                    logger.warning(f"Failed to close stream, status: {response.status}")
        except Exception as e:
            logger.warning(f"Exception while closing stream: {e}")
    
    async def _start_acestream_fetch(self, ongoing: OngoingStream):
        """Fetch stream from AceStream and distribute to all clients"""
        logger.info(f"Starting AceStream fetch for {ongoing.stream_id}")
        
        # Set timeout for reading from AceStream
        timeout = aiohttp.ClientTimeout(sock_read=self.empty_timeout)
        
        try:
            logger.debug(f"Connecting to AceStream playback URL: {ongoing.acestream.playback_url}")
            async with self.session.get(ongoing.acestream.playback_url, timeout=timeout) as ace_response:
                logger.debug(f"AceStream response status: {ace_response.status}")
                if ace_response.status != 200:
                    logger.error(f"AceStream returned status {ace_response.status}")
                    ongoing.started.set()  # Signal error
                    return
                
                # Signal that connection is established BEFORE reading chunks
                ongoing.started.set()
                logger.info(f"AceStream connection established for {ongoing.stream_id}, starting to read chunks")
                
                # Read chunks and distribute to all clients
                chunk_count = 0
                last_cleanup = asyncio.get_event_loop().time()
                async for chunk in ace_response.content.iter_chunked(8192):
                    if not chunk:
                        break
                    
                    chunk_count += 1
                    if chunk_count % 100 == 0:
                        logger.debug(f"Stream {ongoing.stream_id} sent {chunk_count} chunks")
                    
                    # Periodically check for stale clients (every 15 seconds)
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_cleanup > 15:
                        last_cleanup = current_time
                        async with ongoing.lock:
                            stale_clients = []
                            for client_response in list(ongoing.clients):
                                last_write = ongoing.client_last_write.get(id(client_response), 0)
                                # If client hasn't received data in 30 seconds, consider it stale
                                if current_time - last_write > 30:
                                    logger.warning(f"Client inactive for {current_time - last_write:.0f}s, removing")
                                    stale_clients.append(client_response)
                            
                            for stale_client in stale_clients:
                                ongoing.clients.discard(stale_client)
                                ongoing.client_last_write.pop(id(stale_client), None)
                                try:
                                    await stale_client.write_eof()
                                except:
                                    pass
                            
                            if stale_clients:
                                logger.info(f"Removed {len(stale_clients)} stale client(s) from stream {ongoing.stream_id}")
                    
                    async with ongoing.lock:
                        # Send to all connected clients
                        dead_clients = []
                        current_time = asyncio.get_event_loop().time()
                        for client_response in list(ongoing.clients):
                            try:
                                await client_response.write(chunk)
                                # Track successful write
                                ongoing.client_last_write[id(client_response)] = current_time
                                # Signal first chunk written
                                if chunk_count == 1:
                                    ongoing.first_chunk.set()
                            except Exception as e:
                                logger.warning(f"Error writing to client: {e}")
                                dead_clients.append(client_response)
                        
                        # Remove dead clients
                        if dead_clients:
                            for dead_client in dead_clients:
                                ongoing.clients.discard(dead_client)
                                # Remove from tracking
                                ongoing.client_last_write.pop(id(dead_client), None)
                                try:
                                    await dead_client.write_eof()
                                except:
                                    pass
                            client_count = len(ongoing.clients)
                            logger.info(f"Removed {len(dead_clients)} dead client(s) from stream {ongoing.stream_id}, {client_count} client(s) remaining")
                        
                        # If no clients left, stop the stream
                        if not ongoing.clients:
                            logger.info(f"No clients left for stream {ongoing.stream_id}, stopping")
                            break
                            
        except asyncio.TimeoutError:
            logger.info(f"Stream {ongoing.stream_id} timed out (no data for {self.empty_timeout}s)")
            ongoing.started.set()  # Signal timeout
        except Exception as e:
            logger.error(f"Error fetching AceStream: {e}")
            ongoing.started.set()  # Signal error
        finally:
            # Clean up all remaining clients
            async with ongoing.lock:
                for client_response in list(ongoing.clients):
                    try:
                        await client_response.write_eof()
                    except:
                        pass
                ongoing.clients.clear()
            
            # Close the stream on AceStream
            await self._close_stream(ongoing.acestream)
            
            # Signal stream is done
            ongoing.done.set()
            
            # Remove stream from active streams
            async with self.streams_lock:
                if ongoing.stream_id in self.streams:
                    del self.streams[ongoing.stream_id]
                    logger.info(f"Stream {ongoing.stream_id} cleaned up")
    
    async def handle_getstream(self, request: web.Request) -> web.StreamResponse:
        """Handle /ace/getstream endpoint"""
        # Get stream ID or infohash from query parameters
        stream_id = request.query.get('id', '')
        infohash = request.query.get('infohash', '')
        
        if not stream_id and not infohash:
            return web.Response(status=400, text="Missing id or infohash parameter")
        
        if stream_id and infohash:
            return web.Response(status=400, text="Only one of id or infohash can be specified")
        
        # Check if PID was provided (not allowed)
        if 'pid' in request.query:
            return web.Response(status=400, text="PID parameter is not allowed")
        
        # Use stream_id or infohash as the key
        key = stream_id or infohash
        
        logger.info(f"Client {request.remote} requesting stream {key} (User-Agent: {request.headers.get('User-Agent', 'unknown')})")
        
        # Get extra parameters
        extra_params = {k: v for k, v in request.query.items() if k not in ('id', 'infohash', 'pid')}
        
        # Get or create ongoing stream
        async with self.streams_lock:
            if key not in self.streams:
                logger.info(f"Creating new stream for {key}")
                try:
                    acestream = await self._fetch_stream_info(stream_id, infohash, extra_params)
                    ongoing = OngoingStream(key, acestream)
                    self.streams[key] = ongoing
                except Exception as e:
                    logger.error(f"Failed to fetch stream info: {e}")
                    return web.Response(status=500, text=f"Failed to start stream: {e}")
            else:
                logger.info(f"Reusing existing stream for {key}")
                ongoing = self.streams[key]
        
        # Create response for this client
        response = web.StreamResponse()
        response.content_type = 'application/x-mpegURL' if self.m3u8_mode else 'video/MP2T'
        if not self.m3u8_mode:
            response.headers['Transfer-Encoding'] = 'chunked'
        
        # Prepare response FIRST (before any checks) to avoid "write before prepare" errors
        # This makes response ready to receive writes immediately when added to clients list
        await response.prepare(request)
        
        # Add client and start stream if needed (mimics Go's StartStream logic exactly)
        need_to_wait = False
        async with ongoing.lock:
            # Add client to the list FIRST (like Go adds writer at line 172)
            ongoing.clients.add(response)
            client_count = len(ongoing.clients)
            logger.info(f"Stream {key} now has {client_count} client(s)")
            
            # Check if stream is already active (like Go checks player != nil at line 178)
            if ongoing.task is None or ongoing.task.done():
                # Stream not active, need to start it
                need_to_wait = True
                ongoing.task = asyncio.create_task(self._start_acestream_fetch(ongoing))
            # else: stream already active, just return (like Go's return at line 179)
        
        # If we just started the stream, wait for first chunk (mimics Go's blocking middleware.Get)
        # This ensures data is ready to flow when client connects
        if need_to_wait:
            try:
                # Wait for connection
                await asyncio.wait_for(ongoing.started.wait(), timeout=10.0)
                # Also wait for first chunk to ensure data is flowing
                await asyncio.wait_for(ongoing.first_chunk.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for stream {key} to start")
                async with ongoing.lock:
                    ongoing.clients.discard(response)
                return web.Response(status=503, text="Stream failed to start")
        
        # Setup cleanup based on mode
        cleanup_timeout = None
        if self.m3u8_mode:
            # In M3U8 mode, use stream timeout
            cleanup_timeout = self.stream_timeout
        
        try:
            # Wait for the stream to finish (client disconnect is handled by write errors)
            await ongoing.done.wait()
            logger.debug(f"Stream finished for {key}")
        except Exception as e:
            logger.debug(f"Client exception: {e}")
        finally:
            # Remove this client from the stream (might already be removed by copier)
            async with ongoing.lock:
                was_present = response in ongoing.clients
                ongoing.clients.discard(response)
                # Clean up tracking
                ongoing.client_last_write.pop(id(response), None)
                client_count = len(ongoing.clients)
                if was_present:
                    logger.info(f"Handler cleanup: removed client from stream {key}, {client_count} client(s) remaining")
                else:
                    logger.debug(f"Handler cleanup: client already removed from stream {key}, {client_count} client(s) remaining")
            
            try:
                await response.write_eof()
            except:
                pass
        
        return response
    
    async def handle_status(self, request: web.Request) -> web.Response:
        """Handle /ace/status endpoint"""
        stream_id = request.query.get('id', '')
        infohash = request.query.get('infohash', '')
        
        async with self.streams_lock:
            # Global status
            if not stream_id and not infohash:
                status = {
                    'streams': len(self.streams)
                }
                return web.json_response(status)
            
            # Specific stream status
            key = stream_id or infohash
            if key in self.streams:
                ongoing = self.streams[key]
                async with ongoing.lock:
                    status = {
                        'clients': len(ongoing.clients),
                        'stream_id': key,
                        'stat_url': ongoing.acestream.stat_url
                    }
                return web.json_response(status)
            else:
                return web.Response(status=404, text="Stream not found")
    
    async def start_server(self, host: str = "0.0.0.0", port: int = 8080):
        """Start the proxy server"""
        self.session = ClientSession()
        
        app = web.Application()
        app.router.add_get('/ace/getstream', self.handle_getstream)
        app.router.add_get('/ace/getstream/', self.handle_getstream)
        app.router.add_get('/ace/status', self.handle_status)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, host, port)
        await site.start()
        
        logger.info(f"PyAcexy proxy started on {host}:{port}")
        logger.info(f"Connecting to AceStream at {self.scheme}://{self.acestream_host}:{self.acestream_port}")
        logger.info(f"Endpoint mode: {'M3U8/HLS' if self.m3u8_mode else 'MPEG-TS'}")
        
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
        help="AceStream middleware host (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ACEXY_PORT", "6878")),
        help="AceStream middleware port (default: 6878)"
    )
    parser.add_argument(
        "--listen-addr",
        default=os.getenv("ACEXY_LISTEN_ADDR", ":8080"),
        help="Address to listen on (format: [host]:port, default: :8080)"
    )
    parser.add_argument(
        "--scheme",
        default=os.getenv("ACEXY_SCHEME", "http"),
        help="AceStream middleware scheme (http/https, default: http)"
    )
    parser.add_argument(
        "--buffer-size",
        type=int,
        default=int(os.getenv("ACEXY_BUFFER_SIZE", str(4 * 1024 * 1024))),
        help="Buffer size in bytes (default: 4MB)"
    )
    parser.add_argument(
        "--m3u8",
        action="store_true",
        default=os.getenv("ACEXY_M3U8", "").lower() == "true",
        help="Enable M3U8/HLS mode (default: False)"
    )
    parser.add_argument(
        "--empty-timeout",
        type=float,
        default=float(os.getenv("ACEXY_EMPTY_TIMEOUT", "60")),
        help="Timeout in seconds for empty stream data (default: 60s)"
    )
    parser.add_argument(
        "--no-response-timeout",
        type=float,
        default=float(os.getenv("ACEXY_NO_RESPONSE_TIMEOUT", "1")),
        help="Timeout in seconds for AceStream middleware response (default: 1s)"
    )
    parser.add_argument(
        "--m3u8-stream-timeout",
        type=float,
        default=float(os.getenv("ACEXY_M3U8_STREAM_TIMEOUT", "60")),
        help="Timeout in seconds for M3U8 stream (default: 60s)"
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
        empty_timeout=args.empty_timeout,
        no_response_timeout=args.no_response_timeout,
        stream_timeout=args.m3u8_stream_timeout,
    )
    
    try:
        asyncio.run(proxy.start_server(listen_host, listen_port))
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
