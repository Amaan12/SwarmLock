from setuptools import find_packages, setup

setup(
    name="swarmlock",
    version="1.0.0",
    description="Multi-Agent File & Directory Locking Coordinator",
    author="Amaan",
    packages=find_packages(),
    py_modules=["agent_lock"],
    include_package_data=True,
    package_data={
        "swarmlock": ["static/*", "static/**/*"],
    },
    install_requires=[
        "pywebview>=5.0.0",
    ],
    entry_points={
        "console_scripts": [
            "swarmlock=agent_lock:main",
        ],
    },
)
