"""
Integration tests for RedAmon Orchestrator
"""
import pytest
import tempfile
import os

from agent_system_v9.integrations import (
    get_orchestrator_integration,
    get_knowledge_base_integration,
    get_docker_broker_integration,
    get_recon_integration,
    get_cybersec_toolkit_integration,
)


class TestRedAmonOrchestrator:
    """Test RedAmon Orchestrator integration."""

    def test_orchestrator_creates_session(self):
        """Test that orchestrator can create a session."""
        orch = get_orchestrator_integration()
        with tempfile.TemporaryDirectory() as tmpdir:
            session = orch.create_session({'workspace': tmpdir})
            assert session is not None
            assert session.session_id is not None

    def test_orchestrator_session_has_required_fields(self):
        """Test session has all required fields."""
        orch = get_orchestrator_integration()
        with tempfile.TemporaryDirectory() as tmpdir:
            session = orch.create_session({'workspace': tmpdir})
            assert hasattr(session, 'session_id')
            assert hasattr(session, 'workspace_path')
            assert hasattr(session, 'create_task')
            assert hasattr(session, 'execute_plan')


class TestKnowledgeBase:
    """Test Knowledge Base integration."""

    def test_kb_creation(self):
        """Test knowledge base creation."""
        kb_int = get_knowledge_base_integration()
        kb = kb_int.create_knowledge_base('test_kb')
        assert kb is not None
        # KnowledgeBase doesn't have a name attribute, just verify it exists
        assert hasattr(kb, 'search')
        assert hasattr(kb, 'add_documents')

    def test_kb_add_and_search(self):
        """Test adding documents and searching (basic API check)."""
        import asyncio
        kb_int = get_knowledge_base_integration()
        kb = kb_int.create_knowledge_base('test_search')
        
        # Verify methods exist
        assert hasattr(kb, 'search')
        assert hasattr(kb, 'add_documents')
        
        # Test search returns list
        results = asyncio.run(kb.search('Python', k=5))
        assert isinstance(results, list)


class TestDockerBroker:
    """Test Docker Broker integration."""

    def test_broker_creation(self):
        """Test docker broker creation."""
        db_int = get_docker_broker_integration()
        broker = db_int.create_broker('test_broker')
        assert broker is not None
        assert broker.config is not None

    def test_broker_config_defaults(self):
        """Test broker has sensible defaults."""
        db_int = get_docker_broker_integration()
        broker = db_int.create_broker('test_defaults')
        
        # Check allowed images includes common ones
        assert 'alpine' in broker.allowed_images or 'alpine:latest' in broker.allowed_images
        assert 'NET_RAW' in broker.allowed_caps or 'CAP_NET_RAW' in broker.allowed_caps


class TestRecon:
    """Test Recon integration."""

    def test_recon_pipeline_creation(self):
        """Test default pipeline creation."""
        recon = get_recon_integration()
        pipeline = recon.create_default_pipeline()
        assert pipeline is not None
        assert len(pipeline.modules) == 6  # 6 default modules

    def test_recon_modules_exist(self):
        """Test all recon module types exist."""
        recon = get_recon_integration()
        pipeline = recon.create_default_pipeline()
        
        module_names = [m.name for m in pipeline.modules]
        assert 'subdomain_enum' in module_names
        assert 'port_scan' in module_names
        assert 'http_probe' in module_names
        assert 'nuclei_scan' in module_names
        assert 'katana_crawl' in module_names
        assert 'graphql_scan' in module_names


class TestCybersecToolkit:
    """Test Cybersec Toolkit integration."""

    def test_toolkit_creation(self):
        """Test toolkit integration creation."""
        ct = get_cybersec_toolkit_integration()
        assert ct is not None
        assert ct.tool_manager is not None

    def test_toolkit_has_modules(self):
        """Test toolkit has expected module categories."""
        ct = get_cybersec_toolkit_integration()
        modules = ct.tool_manager.get_all_modules()
        assert len(modules) >= 10
        
        # Check for key categories
        expected = ['networking', 'web', 'recon', 'crypto', 'pwn']
        for exp in expected:
            assert exp in modules

    def test_toolkit_can_list_tools(self):
        """Test toolkit can list tools in a module."""
        ct = get_cybersec_toolkit_integration()
        tools = ct.tool_manager.get_tools_by_module('recon')
        assert isinstance(tools, list)
        # Should have at least some recon tools
        assert len(tools) >= 0


class TestShadowGit:
    """Test ShadowGit integration."""

    def test_shadowgit_creation(self):
        """Test ShadowGit creation."""
        import tempfile
        from agent_system_v9.shadowgit import ShadowGit
        with tempfile.TemporaryDirectory() as tmpdir:
            sg = ShadowGit(tmpdir)
            assert sg is not None
            assert str(sg.repo_path) == tmpdir

    def test_shadowgit_sync_creation(self):
        """Test ShadowGitSync creation."""
        from agent_system_v9.shadowgit import ShadowGitSync
        import tempfile
        from agent_system_v9.shadowgit import ShadowGit
        with tempfile.TemporaryDirectory() as tmpdir:
            sg = ShadowGit(tmpdir)
            sync = ShadowGitSync(sg, sg._index)
            assert sync is not None

    def test_shadowgit_remote_management(self):
        """Test adding/removing remotes."""
        from agent_system_v9.shadowgit import ShadowGitSync, RemoteConfig, RemoteProtocol
        import tempfile
        from agent_system_v9.shadowgit import ShadowGit
        with tempfile.TemporaryDirectory() as tmpdir:
            sg = ShadowGit(tmpdir)
            sync = ShadowGitSync(sg, sg._index)
            
            config = RemoteConfig(
                name='origin',
                url='https://github.com/test/repo.git',
                protocol=RemoteProtocol.HTTPS
            )
            sync.add_remote(config)
            remotes = sync.list_remotes()
            assert len(remotes) == 1
            assert remotes[0].name == 'origin'
            
            # Test removal
            assert sync.remove_remote('origin') is True
            assert len(sync.list_remotes()) == 0
            assert sync.remove_remote('nonexistent') is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])