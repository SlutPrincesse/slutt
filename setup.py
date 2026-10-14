#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name="agent_system_v9",
    version="9.0.0",
    description="NEURO-CRANIAL OVERLORD",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "agent-v9=main:main",
            "agent-system-v9=main:main",
        ],
    },
    python_requires=">=3.10",
)
