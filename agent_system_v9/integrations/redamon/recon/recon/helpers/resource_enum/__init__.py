"""
RedAmon - Resource Enumeration Helpers
======================================

This package contains helper functions for resource enumeration:

- form_helpers: HTML form parsing and extraction
- classification: Parameter and endpoint classification
- gau_helpers: GAU passive URL discovery from web archives
- kiterunner_helpers: Kiterunner API endpoint bruteforcing
- katana_helpers: Katana active web crawling
- endpoint_helpers: Endpoint organization and structuring
"""

# Form parsing
# Arjun helpers
from .arjun_helpers import (
    arjun_binary_check,
    merge_arjun_into_by_base_url,
    run_arjun_discovery,
)

# Classification
from .classification import (
    PARAM_PATTERNS,
    classify_endpoint,
    classify_parameter,
    infer_parameter_type,
)

# Endpoint organization
from .endpoint_helpers import (
    organize_endpoints,
)

# FFuf helpers
from .ffuf_helpers import (
    merge_ffuf_into_by_base_url,
    pull_ffuf_binary_check,
    run_ffuf_discovery,
    select_base_paths,
)
from .form_helpers import (
    FormParser,
    parse_forms_from_html,
)

# GAU helpers
from .gau_helpers import (
    detect_gau_methods,
    filter_gau_url,
    merge_gau_into_by_base_url,
    parse_gau_url_to_endpoint,
    pull_gau_docker_image,
    run_gau_discovery,
    run_gau_for_domain,
    verify_gau_urls,
)

# Hakrawler helpers
from .hakrawler_helpers import (
    hakrawler_job_budget,
    merge_hakrawler_into_by_base_url,
    pull_hakrawler_docker_image,
    run_hakrawler_crawler,
)

# jsluice helpers
from .jsluice_helpers import (
    DEFAULT_JSLUICE_EXCLUDE_PATTERNS,
    filter_jsluice_url,
    merge_jsluice_into_by_base_url,
    run_jsluice_analysis,
    verify_jsluice_urls,
)

# Katana helpers
from .katana_helpers import (
    fetch_forms_from_urls,
    pull_katana_docker_image,
    run_katana_crawler,
)

# Kiterunner helpers
from .kiterunner_helpers import (
    detect_kiterunner_methods,
    ensure_kiterunner_binary,
    merge_kiterunner_into_by_base_url,
    run_kiterunner_discovery,
)

# ParamSpider helpers
from .paramspider_helpers import (
    merge_paramspider_into_by_base_url,
    run_paramspider_discovery,
)

# ZAP Ajax Spider helpers
from .zap_ajax_spider_helpers import (
    build_zap_ajax_automation_plan,
    filter_zap_ajax_urls,
    mask_zap_ajax_header_line,
    merge_zap_ajax_into_by_base_url,
    parse_zap_ajax_export_urls,
    parse_zap_ajax_header_lines,
    pull_zap_ajax_docker_image,
    run_zap_ajax_spider,
)

__all__ = [
    # Form parsing
    "FormParser",
    "parse_forms_from_html",
    # Classification
    "PARAM_PATTERNS",
    "classify_parameter",
    "infer_parameter_type",
    "classify_endpoint",
    # GAU
    "pull_gau_docker_image",
    "filter_gau_url",
    "run_gau_for_domain",
    "run_gau_discovery",
    "parse_gau_url_to_endpoint",
    "verify_gau_urls",
    "detect_gau_methods",
    "merge_gau_into_by_base_url",
    # Kiterunner
    "ensure_kiterunner_binary",
    "run_kiterunner_discovery",
    "merge_kiterunner_into_by_base_url",
    "detect_kiterunner_methods",
    # Katana
    "run_katana_crawler",
    "fetch_forms_from_urls",
    "pull_katana_docker_image",
    # Hakrawler
    "hakrawler_job_budget",
    "run_hakrawler_crawler",
    "pull_hakrawler_docker_image",
    "merge_hakrawler_into_by_base_url",
    # jsluice
    "DEFAULT_JSLUICE_EXCLUDE_PATTERNS",
    "filter_jsluice_url",
    "run_jsluice_analysis",
    "merge_jsluice_into_by_base_url",
    "verify_jsluice_urls",
    # ZAP Ajax Spider
    "pull_zap_ajax_docker_image",
    "run_zap_ajax_spider",
    "merge_zap_ajax_into_by_base_url",
    "parse_zap_ajax_header_lines",
    "mask_zap_ajax_header_line",
    "build_zap_ajax_automation_plan",
    "parse_zap_ajax_export_urls",
    "filter_zap_ajax_urls",
    # FFuf
    "run_ffuf_discovery",
    "pull_ffuf_binary_check",
    "merge_ffuf_into_by_base_url",
    "select_base_paths",
    # Arjun
    "arjun_binary_check",
    "run_arjun_discovery",
    "merge_arjun_into_by_base_url",
    # ParamSpider
    "run_paramspider_discovery",
    "merge_paramspider_into_by_base_url",
    # Endpoint organization
    "organize_endpoints",
]
