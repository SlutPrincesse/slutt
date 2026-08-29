"""Allow running as `python -m nexus.browser`."""
from nexus.browser.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
