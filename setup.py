from setuptools import setup, find_packages

setup(
    name="agent-smith",
    version="1.0.0",
    author="Agent Smith Contributors",
    description="Autonomous AI Agent with Graph Memory (IKKF)",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "fastapi",
        "uvicorn",
        "llama-cpp-python",
        "psutil",
        "duckduckgo-search",
        "python-telegram-bot",
        "chromadb",
        "pydantic",
        "beautifulsoup4",
    ],
    entry_points={
        "console_scripts": [
            "agent-smith=main:run_agent",
        ],
    },
    python_requires=">=3.10",
)
