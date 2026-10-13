"""
RedAmon Recon Integration - Recon modules for AGENT_SYSTEM_V9
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ReconModuleType(Enum):
    """Types of recon modules."""
    SUBDOMAIN = "subdomain"
    PORT_SCAN = "port_scan"
    HTTP_PROBE = "http_probe"
    TECH_DETECT = "tech_detect"
    VULN_SCAN = "vuln_scan"
    GRAPHQL = "graphql"
    DNS = "dns"
    SSL_TLS = "ssl_tls"
    CONTENT = "content"
    CLOUD = "cloud"


@dataclass
class ReconTarget:
    """Target for reconnaissance."""
    target: str
    target_type: str  # domain, ip, cidr, url
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconResult:
    """Result from a recon module."""
    module: str
    module_type: ReconModuleType
    target: ReconTarget
    success: bool
    data: Any = None
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ReconModule:
    """Base class for recon modules."""

    def __init__(self, name: str, module_type: ReconModuleType, config: dict | None = None):
        self.name = name
        self.module_type = module_type
        self.config = config or {}
        self._docker_broker = None

    async def run(self, target: ReconTarget) -> ReconResult:
        """Run the recon module."""
        raise NotImplementedError

    def set_docker_broker(self, broker):
        """Set docker broker for container execution."""
        self._docker_broker = broker


class SubdomainEnumModule(ReconModule):
    """Subdomain enumeration using subfinder, amass, etc."""

    def __init__(self, config: dict | None = None):
        super().__init__("subdomain_enum", ReconModuleType.SUBDOMAIN, config)
        self.tools = config.get("tools", ["subfinder", "amass", "puredns"])

    async def run(self, target: ReconTarget) -> ReconResult:
        result = ReconResult(
            module=self.name,
            module_type=self.module_type,
            target=target
        )

        subdomains = set()

        for tool in self.tools:
            try:
                if tool == "subfinder":
                    subs = await self._run_subfinder(target.target)
                elif tool == "amass":
                    subs = await self._run_amass(target.target)
                elif tool == "puredns":
                    subs = await self._run_puredns(target.target)
                else:
                    continue

                subdomains.update(subs)

            except Exception as e:
                logger.warning(f"{tool} failed: {e}")

        result.success = True
        result.data = list(subdomains)
        result.completed_at = datetime.now()
        result.duration = (result.completed_at - result.started_at).total_seconds()

        return result

    async def _run_subfinder(self, domain: str) -> list[str]:
        cmd = ["subfinder", "-d", domain, "-silent"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return [line.strip() for line in stdout.decode().splitlines() if line.strip()]

    async def _run_amass(self, domain: str) -> list[str]:
        cmd = ["amass", "enum", "-d", domain, "-passive"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return [line.strip() for line in stdout.decode().splitlines() if line.strip()]

    async def _run_puredns(self, domain: str) -> list[str]:
        cmd = ["puredns", "resolve", domain]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return [line.strip() for line in stdout.decode().splitlines() if line.strip()]


class PortScanModule(ReconModule):
    """Port scanning using naabu, nmap, rustscan."""

    def __init__(self, config: dict | None = None):
        super().__init__("port_scan", ReconModuleType.PORT_SCAN, config)
        self.tools = config.get("tools", ["naabu", "rustscan"])
        self.ports = config.get("ports", "top-1000")
        self.rate = config.get("rate", 1000)

    async def run(self, target: ReconTarget) -> ReconResult:
        result = ReconResult(
            module=self.name,
            module_type=self.module_type,
            target=target
        )

        open_ports = {}

        for tool in self.tools:
            try:
                if tool == "naabu":
                    ports = await self._run_naabu(target.target)
                elif tool == "rustscan":
                    ports = await self._run_rustscan(target.target)
                else:
                    continue

                for port in ports:
                    if port not in open_ports:
                        open_ports[port] = {"tool": tool}
                    else:
                        open_ports[port]["tool"] += f",{tool}"

            except Exception as e:
                logger.warning(f"{tool} failed: {e}")

        result.success = True
        result.data = open_ports
        result.completed_at = datetime.now()
        result.duration = (result.completed_at - result.started_at).total_seconds()

        return result

    async def _run_naabu(self, target: str) -> list[int]:
        cmd = ["naabu", "-host", target, "-p", self.ports, "-rate", str(self.rate), "-silent"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        ports = []
        for line in stdout.decode().splitlines():
            if ":" in line:
                port = int(line.split(":")[-1])
                ports.append(port)
        return ports

    async def _run_rustscan(self, target: str) -> list[int]:
        cmd = ["rustscan", "-a", target, "-p", self.ports, "--", "-T4"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        ports = []
        for line in stdout.decode().splitlines():
            if "Open" in line and "->" in line:
                parts = line.split("->")[1].strip().split(",")
                for p in parts:
                    if p.strip().isdigit():
                        ports.append(int(p.strip()))
        return ports


class HTTPProbeModule(ReconModule):
    """HTTP probing using httpx."""

    def __init__(self, config: dict | None = None):
        super().__init__("http_probe", ReconModuleType.HTTP_PROBE, config)
        self.ports = config.get("ports", "80,443,8080,8443")
        self.follow_redirects = config.get("follow_redirects", True)
        self.tech_detect = config.get("tech_detect", True)

    async def run(self, target: ReconTarget) -> ReconResult:
        result = ReconResult(
            module=self.name,
            module_type=self.module_type,
            target=target
        )

        try:
            if self._docker_broker:
                # Use Docker broker
                cmd = ["httpx", "-u", target.target, "-ports", self.ports,
                       "-json", "-follow-redirects" if self.follow_redirects else "",
                       "-tech-detect" if self.tech_detect else ""]
            else:
                cmd = ["httpx", "-u", target.target, "-ports", self.ports,
                       "-json", "-follow-redirects" if self.follow_redirects else "",
                       "-tech-detect" if self.tech_detect else ""]

            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            results = []
            for line in stdout.decode().splitlines():
                if line.strip():
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

            result.success = True
            result.data = results

        except Exception as e:
            result.success = False
            result.error = str(e)

        result.completed_at = datetime.now()
        result.duration = (result.completed_at - result.started_at).total_seconds()

        return result


class NucleiScanModule(ReconModule):
    """Vulnerability scanning using nuclei."""

    def __init__(self, config: dict | None = None):
        super().__init__("nuclei_scan", ReconModuleType.VULN_SCAN, config)
        self.templates = config.get("templates", [])
        self.severity = config.get("severity", ["critical", "high", "medium"])
        self.rate_limit = config.get("rate_limit", 150)

    async def run(self, target: ReconTarget) -> ReconResult:
        result = ReconResult(
            module=self.name,
            module_type=self.module_type,
            target=target
        )

        try:
            cmd = ["nuclei", "-u", target.target, "-silent", "-json"]

            if self.templates:
                for t in self.templates:
                    cmd.extend(["-t", t])

            if self.severity:
                cmd.extend(["-severity", ",".join(self.severity)])

            cmd.extend(["-rate-limit", str(self.rate_limit)])

            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            findings = []
            for line in stdout.decode().splitlines():
                if line.strip():
                    try:
                        findings.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

            result.success = True
            result.data = findings

        except Exception as e:
            result.success = False
            result.error = str(e)

        result.completed_at = datetime.now()
        result.duration = (result.completed_at - result.started_at).total_seconds()

        return result


class KatanaCrawlModule(ReconModule):
    """Web crawling using katana."""

    def __init__(self, config: dict | None = None):
        super().__init__("katana_crawl", ReconModuleType.CONTENT, config)
        self.depth = config.get("depth", 2)
        self.js_crawl = config.get("js_crawl", True)
        self.known_files = config.get("known_files", True)

    async def run(self, target: ReconTarget) -> ReconResult:
        result = ReconResult(
            module=self.name,
            module_type=self.module_type,
            target=target
        )

        try:
            cmd = ["katana", "-u", target.target, "-silent", "-json"]
            cmd.extend(["-d", str(self.depth)])

            if self.js_crawl:
                cmd.append("-jc")

            if self.known_files:
                cmd.append("-kf")

            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            urls = []
            for line in stdout.decode().splitlines():
                if line.strip():
                    try:
                        urls.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

            result.success = True
            result.data = urls

        except Exception as e:
            result.success = False
            result.error = str(e)

        result.completed_at = datetime.now()
        result.duration = (result.completed_at - result.started_at).total_seconds()

        return result


class GraphQLScannerModule(ReconModule):
    """GraphQL endpoint scanning."""

    def __init__(self, config: dict | None = None):
        super().__init__("graphql_scan", ReconModuleType.GRAPHQL, config)
        self.introspection = config.get("introspection", True)
        self.tools = config.get("tools", ["graphql-cop"])

    async def run(self, target: ReconTarget) -> ReconResult:
        result = ReconResult(
            module=self.name,
            module_type=self.module_type,
            target=target
        )

        findings = []

        for tool in self.tools:
            try:
                if tool == "graphql-cop":
                    tool_findings = await self._run_graphql_cop(target.target)
                    findings.extend(tool_findings)
            except Exception as e:
                logger.warning(f"{tool} failed: {e}")

        result.success = True
        result.data = findings
        result.completed_at = datetime.now()
        result.duration = (result.completed_at - result.started_at).total_seconds()

        return result

    async def _run_graphql_cop(self, url: str) -> list[dict]:
        cmd = ["graphql-cop", "-u", url]
        if self.introspection:
            cmd.append("-i")

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()

        findings = []
        for line in stdout.decode().splitlines():
            if line.strip() and "ERROR" not in line and "WARN" not in line:
                findings.append({"message": line.strip()})

        return findings


class ReconPipeline:
    """Orchestrates multiple recon modules in sequence/parallel."""

    def __init__(self, modules: list[ReconModule] = None):
        self.modules = modules or []
        self._docker_broker = None

    def add_module(self, module: ReconModule):
        """Add a recon module."""
        self.modules.append(module)
        if self._docker_broker:
            module.set_docker_broker(self._docker_broker)

    def set_docker_broker(self, broker):
        """Set docker broker for all modules."""
        self._docker_broker = broker
        for module in self.modules:
            module.set_docker_broker(broker)

    async def run(self, target: ReconTarget,
                  parallel: bool = False) -> list[ReconResult]:
        """Run all modules against target."""
        if parallel:
            tasks = [module.run(target) for module in self.modules]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return [r if isinstance(r, ReconResult) else ReconResult(
                module="unknown", module_type=ReconModuleType.SUBDOMAIN,
                target=target, success=False, error=str(r)
            ) for r in results]
        results = []
        for module in self.modules:
            result = await module.run(target)
            results.append(result)
        return results


class ReconIntegration:
    """High-level integration for AGENT_SYSTEM_V9."""

    def __init__(self):
        self._pipelines: dict[str, ReconPipeline] = {}
        self._default_pipeline: ReconPipeline | None = None

    def create_pipeline(self, name: str, modules: list[ReconModule] = None) -> ReconPipeline:
        """Create a named recon pipeline."""
        pipeline = ReconPipeline(modules)
        self._pipelines[name] = pipeline
        return pipeline

    def get_pipeline(self, name: str) -> ReconPipeline | None:
        """Get pipeline by name."""
        return self._pipelines.get(name)

    def set_default_pipeline(self, pipeline: ReconPipeline):
        """Set default pipeline."""
        self._default_pipeline = pipeline

    def get_default_pipeline(self) -> ReconPipeline | None:
        """Get default pipeline."""
        return self._default_pipeline

    def create_default_pipeline(self, config: dict | None = None) -> ReconPipeline:
        """Create a default comprehensive pipeline."""
        modules = [
            SubdomainEnumModule(config.get("subdomain") if config else None),
            PortScanModule(config.get("port_scan") if config else None),
            HTTPProbeModule(config.get("http_probe") if config else None),
            NucleiScanModule(config.get("nuclei") if config else None),
            KatanaCrawlModule(config.get("katana") if config else None),
            GraphQLScannerModule(config.get("graphql") if config else None),
        ]

        pipeline = ReconPipeline(modules)
        self._default_pipeline = pipeline
        return pipeline

    async def run_recon(self, target: str, target_type: str = "domain",
                        pipeline_name: str = None, parallel: bool = False) -> list[ReconResult]:
        """Run reconnaissance on target."""
        target_obj = ReconTarget(target=target, target_type=target_type)

        pipeline = self._pipelines.get(pipeline_name) if pipeline_name else self._default_pipeline
        if not pipeline:
            pipeline = self.create_default_pipeline()

        return await pipeline.run(target_obj, parallel)

    def list_pipelines(self) -> list[str]:
        """List pipeline names."""
        return list(self._pipelines.keys())


_recon_integration: ReconIntegration | None = None


def get_recon_integration() -> ReconIntegration:
    """Get global recon integration."""
    global _recon_integration
    if _recon_integration is None:
        _recon_integration = ReconIntegration()
    return _recon_integration
