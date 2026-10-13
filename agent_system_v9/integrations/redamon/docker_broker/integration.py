"""
RedAmon Docker Broker Integration - Secure Docker socket proxy for AGENT_SYSTEM_V9
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DockerBrokerConfig:
    """Configuration for Docker broker."""
    upstream_socket: str = "/var/run/docker.sock"
    listen_socket: str = "/run/broker/docker.sock"
    allowed_images: set[str] = field(default_factory=set)
    allowed_bind_prefixes: list[str] = field(default_factory=list)
    allowed_volumes: set[str] = field(default_factory=set)
    allowed_rw_prefixes: list[str] = field(default_factory=list)
    allowed_rw_volumes: set[str] = field(default_factory=set)
    allowed_caps: set[str] = field(default_factory=set)


_DEFAULT_ALLOWED_IMAGES = {
    "projectdiscovery/naabu:latest",
    "projectdiscovery/httpx:latest",
    "projectdiscovery/katana:latest",
    "projectdiscovery/nuclei:latest",
    "projectdiscovery/uncover:latest",
    "projectdiscovery/subfinder:latest",
    "projectdiscovery/tlsx:latest",
    "caffix/amass:latest",
    "frost19k/puredns:latest",
    "sxcurity/gau:latest",
    "sxcurity/gau:arm64",
    "jauderho/hakrawler:latest",
    "ghcr.io/zaproxy/zaproxy:stable",
    "dolevf/graphql-cop:1.14",
    "alpine",
    "alpine:latest",
}

_DEFAULT_BIND_PREFIXES = ["/tmp/redamon"]
_DEFAULT_VOLUMES = {"nuclei-templates", "redamon-osv-db", "redamon-sca-intel"}
_DEFAULT_RW_PREFIXES = ["/tmp/redamon"]
_DEFAULT_RW_VOLUMES = set()
_DEFAULT_CAPS = {"NET_RAW", "NET_ADMIN", "CAP_NET_RAW", "CAP_NET_ADMIN"}


def _canonical_image(image: str) -> str:
    """Canonicalize Docker image reference for allowlist matching."""
    if not image:
        return image
    image = urllib.parse.unquote(image)
    for prefix in ("index.docker.io/", "docker.io/"):
        if image.startswith(prefix):
            image = image[len(prefix):]
            break
    if image.startswith("library/"):
        image = image[len("library/"):]
    return image


class DockerBroker:
    """
    Secure Docker socket broker - filters dangerous container creation requests.
    Integrates RedAmon's docker_broker into AGENT_SYSTEM_V9 kernel/sandbox.
    """

    def __init__(self, config: DockerBrokerConfig | None = None):
        self.config = config or DockerBrokerConfig()
        self._server: asyncio.Server | None = None
        self._running = False

        # Merge defaults with config
        self.allowed_images = {_canonical_image(i) for i in
            (_DEFAULT_ALLOWED_IMAGES | self.config.allowed_images)}
        self.allowed_bind_prefixes = _DEFAULT_BIND_PREFIXES + self.config.allowed_bind_prefixes
        self.allowed_volumes = _DEFAULT_VOLUMES | self.config.allowed_volumes
        self.allowed_rw_prefixes = _DEFAULT_RW_PREFIXES + self.config.allowed_rw_prefixes
        self.allowed_rw_volumes = _DEFAULT_RW_VOLUMES | self.config.allowed_rw_volumes
        self.allowed_caps = _DEFAULT_CAPS | self.config.allowed_caps

        # Compile regexes
        self._create_re = re.compile(r"^/(v[\d.]+/)?containers/create$")
        self._hijack_re = re.compile(r"^/(v[\d.]+/)?(containers/[^/]+/attach|exec/[^/]+/start)$")
        self._images_create_re = re.compile(r"^/(v[\d.]+/)?images/create$")

    async def start(self):
        """Start the broker server."""
        if self._running:
            return

        # Ensure listen directory exists
        listen_path = Path(self.config.listen_socket)
        listen_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing socket
        if listen_path.exists():
            listen_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(listen_path)
        )

        self._running = True
        logger.info(f"Docker broker started on {self.config.listen_socket}")

    async def stop(self):
        """Stop the broker server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        listen_path = Path(self.config.listen_socket)
        if listen_path.exists():
            listen_path.unlink()

        self._running = False
        logger.info("Docker broker stopped")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming client connection."""
        try:
            # Read request
            request_line = await reader.readline()
            if not request_line:
                return

            # Parse request line
            parts = request_line.decode().strip().split()
            if len(parts) < 3:
                return

            method, path, version = parts[0], parts[1], parts[2]

            # Read headers
            headers = {}
            content_length = 0
            while True:
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break
                header_line = line.decode().strip()
                if ": " in header_line:
                    key, value = header_line.split(": ", 1)
                    headers[key.lower()] = value
                    if key.lower() == "content-length":
                        content_length = int(value)

            # Read body if present
            body = b""
            if content_length > 0:
                body = await reader.readexactly(content_length)

            # Check if this is a container create request
            if method == "POST" and self._create_re.match(path):
                allowed, error = self._validate_container_create(body)
                if not allowed:
                    await self._send_response(writer, 403, {"error": error})
                    return

            # Check if this is a pull request
            if method == "POST" and self._images_create_re.match(path):
                # Allow pulls to allowed images
                allowed = True  # Could add validation here

            # Forward to upstream
            await self._forward_request(writer, method, path, version, headers, body)

        except Exception as e:
            logger.error(f"Error handling client: {e}")
            try:
                await self._send_response(writer, 500, {"error": str(e)})
            except Exception:
                pass
        finally:
            writer.close()
            await writer.wait_closed()

    def _validate_container_create(self, body: bytes) -> tuple[bool, str]:
        """Validate container creation request against policy."""
        try:
            spec = json.loads(body.decode())
        except json.JSONDecodeError:
            return False, "Invalid JSON"

        # Check image
        image = spec.get("Image", "")
        canonical = _canonical_image(image)
        if canonical not in self.allowed_images:
            return False, f"Image not allowed: {canonical}"

        # Check host config
        host_config = spec.get("HostConfig", {})

        # Check binds
        binds = host_config.get("Binds", [])
        for bind in binds:
            if not self._validate_bind(bind):
                return False, f"Bind not allowed: {bind}"

        # Check volumes
        volumes = host_config.get("Volumes", {}) or {}
        for vol_path in volumes:
            if not self._validate_volume(vol_path):
                return False, f"Volume not allowed: {vol_path}"

        # Check capabilities
        cap_add = host_config.get("CapAdd", []) or []
        for cap in cap_add:
            if cap not in self.allowed_caps:
                return False, f"Capability not allowed: {cap}"

        # Check privileged
        if host_config.get("Privileged", False):
            return False, "Privileged containers not allowed"

        # Check network mode
        network_mode = host_config.get("NetworkMode", "")
        if network_mode in ("host", "none"):
            pass  # Allow host/none
        elif network_mode.startswith("container:"):
            return False, "Container network mode not allowed"

        # Check pid mode
        if host_config.get("PidMode", "") == "host":
            return False, "Host PID mode not allowed"

        # Check ipc mode
        if host_config.get("IpcMode", "") == "host":
            return False, "Host IPC mode not allowed"

        # Check security opt
        security_opt = host_config.get("SecurityOpt", []) or []
        for opt in security_opt:
            if "apparmor:unconfined" in opt or "seccomp:unconfined" in opt:
                return False, f"Security opt not allowed: {opt}"

        return True, ""

    def _validate_bind(self, bind: str) -> bool:
        """Validate a bind mount specification."""
        # Format: source:dest:mode or source:dest
        parts = bind.split(":")
        if len(parts) < 2:
            return False

        source = parts[0]

        # Named volume
        if not source.startswith("/"):
            return source in self.allowed_volumes

        # Host path - check against allowed prefixes
        for prefix in self.allowed_bind_prefixes:
            if source.startswith(prefix):
                # Check if read-write
                mode = parts[2] if len(parts) > 2 else "rw"
                if "rw" in mode:
                    for rw_prefix in self.allowed_rw_prefixes:
                        if source.startswith(rw_prefix):
                            return True
                    return False  # RW not allowed for this prefix
                return True  # Read-only allowed

        return False

    def _validate_volume(self, volume: str) -> bool:
        """Validate a volume specification."""
        return volume in self.allowed_volumes

    async def _forward_request(self, client_writer: asyncio.StreamWriter,
                                method: str, path: str, version: str,
                                headers: dict[str, str], body: bytes):
        """Forward request to upstream Docker socket."""
        # Connect to upstream
        upstream_reader, upstream_writer = await asyncio.open_unix_connection(
            self.config.upstream_socket
        )

        try:
            # Add Connection: close to prevent keep-alive
            headers["connection"] = "close"

            # Write request to upstream
            request = f"{method} {path} {version}\r\n"
            for key, value in headers.items():
                request += f"{key}: {value}\r\n"
            request += "\r\n"
            upstream_writer.write(request.encode())
            if body:
                upstream_writer.write(body)
            await upstream_writer.drain()

            # Check if hijack endpoint
            if self._hijack_re.match(path):
                await self._pipe_hijack(client_writer, upstream_reader, upstream_writer)
            else:
                await self._relay_response(client_writer, upstream_reader)

        finally:
            upstream_writer.close()
            await upstream_writer.wait_closed()

    async def _relay_response(self, client_writer: asyncio.StreamWriter,
                               upstream_reader: asyncio.StreamReader):
        """Relay response from upstream to client."""
        # Read status line
        status_line = await upstream_reader.readline()
        if not status_line:
            return
        client_writer.write(status_line)

        # Read headers
        content_length = 0
        chunked = False
        while True:
            line = await upstream_reader.readline()
            if not line or line == b"\r\n":
                break
            client_writer.write(line)
            header_line = line.decode().strip().lower()
            if header_line.startswith("content-length:"):
                content_length = int(header_line.split(":")[1].strip())
            elif header_line.startswith("transfer-encoding:") and "chunked" in header_line:
                chunked = True

        await client_writer.drain()

        if chunked:
            # Relay chunked encoding
            while True:
                chunk_line = await upstream_reader.readline()
                if not chunk_line:
                    break
                client_writer.write(chunk_line)
                await client_writer.drain()
                chunk_size = int(chunk_line.decode().strip(), 16)
                if chunk_size == 0:
                    # Read final CRLF and trailers
                    client_writer.write(await upstream_reader.readline())
                    await client_writer.drain()
                    break
                chunk_data = await upstream_reader.readexactly(chunk_size + 2)  # data + CRLF
                client_writer.write(chunk_data)
                await client_writer.drain()
        # Read exact content length
        elif content_length > 0:
            data = await upstream_reader.readexactly(content_length)
            client_writer.write(data)
            await client_writer.drain()

    async def _pipe_hijack(self, client_writer: asyncio.StreamWriter,
                           upstream_reader: asyncio.StreamReader,
                           upstream_writer: asyncio.StreamWriter):
        """Pipe bidirectional data for hijack endpoints."""
        # Send initial headers first
        await self._relay_response(client_writer, upstream_reader)

        # Then pipe raw data
        async def pipe(src, dst):
            try:
                while True:
                    data = await src.read(4096)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            except Exception:
                pass

        await asyncio.gather(
            pipe(client_writer, upstream_writer),
            pipe(upstream_reader, client_writer)
        )

    async def _send_response(self, writer: asyncio.StreamWriter, status: int, data: dict[str, Any]):
        """Send HTTP response."""
        body = json.dumps(data).encode()
        response = (
            f"HTTP/1.1 {status} Forbidden\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode() + body
        writer.write(response)
        await writer.drain()


class DockerBrokerIntegration:
    """Integration wrapper for AGENT_SYSTEM_V9."""

    def __init__(self):
        self._brokers: dict[str, DockerBroker] = {}

    def create_broker(self, name: str, config: DockerBrokerConfig | None = None) -> DockerBroker:
        """Create a named broker."""
        broker = DockerBroker(config)
        self._brokers[name] = broker
        return broker

    def get_broker(self, name: str) -> DockerBroker | None:
        """Get broker by name."""
        return self._brokers.get(name)

    async def start_all(self):
        """Start all brokers."""
        for broker in self._brokers.values():
            await broker.start()

    async def stop_all(self):
        """Stop all brokers."""
        for broker in self._brokers.values():
            await broker.stop()

    def list_brokers(self) -> list[str]:
        """List broker names."""
        return list(self._brokers.keys())


_docker_broker_integration: DockerBrokerIntegration | None = None


def get_docker_broker_integration() -> DockerBrokerIntegration:
    """Get global docker broker integration."""
    global _docker_broker_integration
    if _docker_broker_integration is None:
        _docker_broker_integration = DockerBrokerIntegration()
    return _docker_broker_integration
