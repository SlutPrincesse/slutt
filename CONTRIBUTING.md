# Contributing to AGENT_SYSTEM_V9

Thank you for your interest in contributing! This document outlines the process and standards for contributing to AGENT_SYSTEM_V9.

## Code of Conduct

By participating, you agree to abide by our Code of Conduct. Please read it before contributing.

## Getting Started

### Prerequisites

- Python 3.10+
- Docker
- Git
- Make (optional, for convenience commands)

### Development Setup

```bash
# Fork and clone
git clone https://github.com/your-fork/agent-system-v9
cd agent-system-v9

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode with all extras
pip install -e ".[dev,ml,distributed,monitoring,docs]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest tests/
```

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Changes

Follow our coding standards:
- Type hints required for all public APIs
- Docstrings for all public classes/functions (Google style)
- Tests for new functionality
- Update documentation as needed

### 3. Run Quality Checks

```bash
# Format code
ruff format .
ruff check --fix .

# Type check
mypy agent_system_v9

# Run tests
pytest tests/ -v

# Security scan
bandit -r agent_system_v9/
```

### 4. Commit Changes

Use conventional commits:

```bash
git commit -m "feat(core): add new capability to PluginManager"
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

## Coding Standards

### Python Style

- **Formatter**: Ruff (Black-compatible)
- **Linter**: Ruff with all rules enabled
- **Type Checker**: MyPy (strict mode for core modules)
- **Import Sorting**: isort (via Ruff)

### Type Hints

```python
# Good
def process_items(items: list[str]) -> dict[str, int]:
    return {item: len(item) for item in items}

# Avoid
def process_items(items):
    return {item: len(item) for item in items}
```

### Docstrings (Google Style)

```python
def process_data(data: list[dict[str, Any]], threshold: float = 0.5) -> list[str]:
    """Process data and return filtered results.

    Args:
        data: List of dictionaries to process.
        threshold: Minimum score threshold (default: 0.5).

    Returns:
        List of processed item names.

    Raises:
        ValueError: If data is empty or threshold is invalid.
    """
    if not data:
        raise ValueError("Data cannot be empty")
    # ... implementation
```

### Testing

- Unit tests in `tests/unit/`
- Integration tests in `tests/integration/`
- Property-based tests in `tests/property/`
- Target: >90% coverage for core modules

```python
# Example test
def test_registry_singleton():
    """Test SystemRegistry is a singleton."""
    reg1 = SystemRegistry()
    reg2 = SystemRegistry()
    assert reg1 is reg2
```

## Pull Request Guidelines

### PR Title

Use conventional commit format:
- `feat(section): description`
- `fix(section): description`
- `docs(section): description`

### PR Description

Include:
1. **What** - Summary of changes
2. **Why** - Motivation/context
3. **How** - Implementation approach
4. **Testing** - How to verify
5. **Breaking Changes** - If any

### Review Checklist

- [ ] Tests pass
- [ ] Type checking passes
- [ ] Linting passes
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
- [ ] Security implications considered

## Release Process

### Versioning

We follow Semantic Versioning (MAJOR.MINOR.PATCH):
- MAJOR: Breaking changes
- MINOR: New features (backward compatible)
- PATCH: Bug fixes

### Release Steps

1. Update `CHANGELOG.md`
2. Create release PR
3. Tag release: `git tag v9.x.x`
4. GitHub Actions builds and publishes

## Adding New Sections

To add a new major subsystem (Section XX):

1. Create directory: `agent_system_v9/new_section/`
2. Implement modules following existing patterns
3. Add `__init__.py` with exports
4. Register in main `__init__.py`
5. Add tests in `tests/unit/test_new_section.py`
6. Update `docs/architecture.md` section map
7. Update `README.md` section list

## Security Reporting

Report security vulnerabilities privately to security@your-org.com. Do not open public issues for security bugs.

## Getting Help

- GitHub Discussions for questions
- GitHub Issues for bugs/features
- Discord/Slack for real-time chat (if available)

## License

By contributing, you agree that your contributions will be licensed under the project's license (MIT/Apache-2.0).