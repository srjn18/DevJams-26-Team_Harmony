from setuptools import setup

setup(
    name="semantic_relevance_engine",
    version="0.1.0",
    description="Semantic Relevance Engine for LLM Context Optimization Middleware",
    packages=["semantic_relevance_engine"],
    package_dir={"semantic_relevance_engine": "."},
    python_requires=">=3.9",
    install_requires=[
        "pydantic>=2.0.0",
        "numpy>=1.20.0",
    ],
    extras_require={
        "local_models": ["sentence-transformers>=2.2.0"],
    },
    entry_points={
        "console_scripts": [
            "semantic-relevance-engine=semantic_relevance_engine.cli:main",
        ],
    },
)
