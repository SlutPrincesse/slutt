"""
RedAmon - Vulnerability Scan Helpers
=====================================

This package contains helper functions organized by category:

- docker_helpers: Docker utilities (container management, image pulls, permissions)
- target_helpers: Target extraction and URL building from recon data
- nuclei_helpers: Nuclei command building, output parsing, false positive detection
- cve_helpers: CVE lookup from NVD and Vulners APIs
- security_checks: Custom security checks (direct IP access, TLS, headers, etc.)
"""

# Standard logging
# CVE lookup
from .cve_helpers import (
    CPE_MAPPINGS,
    NVD_API_URL,
    VULNERS_API_URL,
    classify_cvss_score,
    lookup_cves_nvd,
    lookup_cves_vulners,
    normalize_product_name,
    parse_technology_string,
    run_cve_lookup,
    split_server_header,
)

# Docker utilities
from .docker_helpers import (
    NUCLEI_TEMPLATES_VOLUME,
    ensure_templates_volume,
    fix_file_ownership,
    get_real_user_ids,
    is_docker_installed,
    is_docker_running,
    pull_katana_docker_image,
    pull_nuclei_docker_image,
)
from .log_helpers import (
    is_sensitive_key,
    print_effective_settings,
)

# Nuclei-specific helpers
from .nuclei_helpers import (
    build_nuclei_command,
    is_false_positive,
    parse_nuclei_finding,
    set_fp_ai_ctx,
)

# Security checks
from .security_checks import (
    run_cert_hygiene_checks_only,
    run_security_checks,
)

# Subdomain takeover helpers
from .takeover_helpers import (
    AUTO_EXPLOITABLE_PROVIDERS,
    BADDNS_DEFAULT_MODULES,
    BADDNS_MODULES,
    PROVIDER_FROM_SIGNAL,
    build_baddns_command,
    build_subjack_command,
    dedupe_findings,
    finding_id,
    normalize_baddns_finding,
    normalize_nuclei_takeover,
    normalize_subjack_result,
    provider_from_cert,
    provider_from_cname,
    provider_from_signal,
    resolve_cname_target,
    score_finding,
)

# Target extraction and URL building
from .target_helpers import (
    build_target_urls,
    build_target_urls_from_httpx,
    build_target_urls_from_resource_enum,
    extract_targets_from_recon,
)

__all__ = [
    # Docker
    "is_docker_installed",
    "is_docker_running",
    "get_real_user_ids",
    "fix_file_ownership",
    "pull_nuclei_docker_image",
    "pull_katana_docker_image",
    "ensure_templates_volume",
    "NUCLEI_TEMPLATES_VOLUME",
    # Targets
    "extract_targets_from_recon",
    "build_target_urls_from_httpx",
    "build_target_urls_from_resource_enum",
    "build_target_urls",
    # Nuclei
    "build_nuclei_command",
    "parse_nuclei_finding",
    "is_false_positive",
    "set_fp_ai_ctx",
    # Katana
    # CVE
    "split_server_header",
    "parse_technology_string",
    "normalize_product_name",
    "classify_cvss_score",
    "lookup_cves_nvd",
    "lookup_cves_vulners",
    "run_cve_lookup",
    "CPE_MAPPINGS",
    "NVD_API_URL",
    "VULNERS_API_URL",
    # Security checks
    "run_security_checks",
    "run_cert_hygiene_checks_only",
    # Takeover
    "build_subjack_command",
    "build_baddns_command",
    "normalize_subjack_result",
    "normalize_nuclei_takeover",
    "normalize_baddns_finding",
    "dedupe_findings",
    "score_finding",
    "finding_id",
    "provider_from_cname",
    "provider_from_cert",
    "provider_from_signal",
    "resolve_cname_target",
    "AUTO_EXPLOITABLE_PROVIDERS",
    "PROVIDER_FROM_SIGNAL",
    "BADDNS_MODULES",
    "BADDNS_DEFAULT_MODULES", "is_sensitive_key", "print_effective_settings",
]
