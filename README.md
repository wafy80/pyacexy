# PyAcexy - Python AceStream Proxy

Python implementation of the AceStream proxy originally written in Go.

## Installation

```bash
pip install -e .
```

## Usage

```bash
pyacexy --help
```

## Features

- AceStream middleware proxy
- Stream multiplexing support
- Automatic PID assignment per client
- MPEG-TS and HLS (M3U8) support

## Configuration

The proxy can be configured using command-line arguments or environment variables:

- `--host`: AceStream middleware host (default: localhost)
- `--port`: AceStream middleware port (default: 6878)
- `--listen-addr`: Address to listen on (default: :8080)
- `--scheme`: AceStream middleware scheme (default: http)

## License

GNU General Public License v3.0
