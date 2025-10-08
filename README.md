# pyacexy

**pyacexy** is a robust Python implementation of an AceStream HTTP proxy. It enables you to stream AceStream content via simple HTTP requests, making integration with media players, automation tools, and custom clients easy and efficient.

---

## Features

- **Pure Python Implementation:** Fast, lightweight, and easy to deploy or customize.
- **AceStream to HTTP Proxy:** Seamlessly converts AceStream streams for HTTP clients.
- **Shell Integration:** Includes helpful shell scripts for service management and automation.
- **Docker Support:** Ready-to-use Dockerfile for quick containerized deployment.
- **Cross-Platform:** Runs on any system with Python 3.x support.

---

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Docker](#docker)
- [Shell Scripts](#shell-scripts)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Installation

### Prerequisites

- Python 3.6 or newer
- [AceStream Engine](https://wiki.acestream.media/Download) installed and running

### Clone the Repository

```bash
git clone https://github.com/wafy80/pyacexy.git
cd pyacexy
```

### Install Requirements

```bash
pip install -r requirements.txt
```

---

## Usage

Start the proxy server:

```bash
python pyacexy.py
```

By default, the server listens on `localhost:8000`. You can change the host and port via command-line arguments or environment variables.

### Example: Streaming with VLC

1. Start the AceStream engine.
2. Start `pyacexy`.
3. Open VLC and enter the following URL:
   ```
   http://localhost:8000/ace/getstream?id=<acestream_content_id>
   ```

---

## Configuration

You can configure pyacexy using:

- Command-line options
- Environment variables
- Editing the script (for advanced customizations)

Refer to the in-script documentation and comments for all available options.

---

## Docker

To run pyacexy in a Docker container:

```bash
docker build -t pyacexy .
docker run -d -p 8000:8000 --name pyacexy pyacexy
```

Ensure that your AceStream Engine is accessible from within the container or map its port appropriately.

---

## Shell Scripts

This repository includes shell scripts to manage and automate the proxy, such as:

- Starting/stopping the proxy service
- Health checks and logs

Scripts are located in the `scripts/` directory.

---

## Contributing

Contributions and pull requests are welcome!

1. Fork the repository
2. Create a new branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a pull request

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgements

- Inspired by [AceStream](https://acestream.org/) and open-source streaming initiatives.
- Special thanks to [@Javinator9889/acexy](https://github.com/Javinator9889/acexy), whose project served as an inspiration for this implementation.

---

**Enjoy seamless AceStream streaming via HTTP with pyacexy!**
