from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="pyacexy",
    version="0.1.0",
    author="Your Name",
    description="Python implementation of AceStream proxy",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Javinator9889/acexy",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "aiohttp>=3.8.0",
        "asyncio",
    ],
    entry_points={
        "console_scripts": [
            "pyacexy=pyacexy.proxy:main",
        ],
    },
)
