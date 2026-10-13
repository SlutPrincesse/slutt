"""Partial Tlsx over every root of a Domain batch.

The collaborator's report that started this work: a TLS grab over a three-root
batch scanned only one root's targets. run_tlsx now hands the builder every
root the run covers plus each root's group scope, and the writer receives the
roots, so SANs under any of them are linked.

Fixture roots are alpha.test / beta.test / gamma.test only.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from recon.partial_recon_modules import tlsx_scanning  # noqa: E402

ROOTS = ["alpha.test", "beta.test", "gamma.test"]
GROUPS = [{"rootDomain": r, "prefixes": ["*"], "batch": True} for r in ROOTS]


def _graph_recon(domains, *_a, **_kw):
    return {
        "domain": domains[0], "domains": list(domains),
        "port_scan": {"by_ip": {"10.0.2.1": {"ip": "10.0.2.1", "hostnames": ["api.beta.test"],
                                             "ports": [993], "port_details": []}},
                      "by_host": {}, "ip_to_hostnames": {}, "all_ports": [993],
                      "scan_metadata": {}, "summary": {}},
        "dns": {"domain": {"ips": {"ipv4": [], "ipv6": []}, "has_records": False}, "subdomains": {}},
        "metadata": {"include_root_domain": False},
    }


@pytest.fixture
def run(monkeypatch):
    client = MagicMock()
    client.verify_connection.return_value = True
    client.update_graph_from_tlsx.return_value = {}
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    fake_graph_db = MagicMock()
    fake_graph_db.Neo4jClient.return_value = client
    builder = MagicMock(side_effect=_graph_recon)
    monkeypatch.setattr(tlsx_scanning, "_build_port_scan_data_from_graph", builder)

    def _run(config):
        with patch.dict(sys.modules, {"graph_db": fake_graph_db}), \
             patch("recon.main_recon_modules.tls_scan.run_tlsx_enrichment",
                   side_effect=lambda rd, settings=None: rd):
            tlsx_scanning.run_tlsx({"_settings": {}, **config})
        return builder, client

    return _run


def test_every_root_and_its_group_reach_the_builder(run):
    builder, _ = run({"domains": ROOTS, "domain": "alpha.test", "domain_groups": GROUPS})
    args, kwargs = builder.call_args
    assert args[0] == ROOTS
    assert kwargs["domain_groups"] == GROUPS


def test_the_writer_gets_every_root(run):
    _, client = run({"domains": ROOTS, "domain": "alpha.test", "domain_groups": GROUPS})
    written = client.update_graph_from_tlsx.call_args.kwargs["recon_data"]
    assert written["domains"] == ROOTS


def test_generic_user_ips_attach_through_the_roots(run):
    _, client = run({"domains": ROOTS, "domain": "alpha.test", "domain_groups": GROUPS,
                     "include_graph_targets": False,
                     "user_targets": {"ips": ["203.0.113.9"], "ports": [993]}})
    kwargs = client.create_user_input_node.call_args.kwargs
    # The mixin resolves the root from the values; IPs name none, so the first.
    assert kwargs["domain"] == ROOTS
    assert kwargs["user_input_data"]["values"] == ["203.0.113.9"]


def test_without_graph_targets_the_skeleton_carries_the_roots(run):
    _, client = run({"domains": ROOTS, "domain": "alpha.test", "include_graph_targets": False,
                     "user_targets": {"ips": ["203.0.113.9"], "ports": [993]}})
    written = client.update_graph_from_tlsx.call_args.kwargs["recon_data"]
    assert written["domain"] == "alpha.test" and written["domains"] == ROOTS


def test_nothing_to_scan_still_exits_1(run):
    with pytest.raises(SystemExit) as ei:
        run({"domains": ROOTS, "domain": "alpha.test", "include_graph_targets": False})
    assert ei.value.code == 1
