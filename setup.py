#!/usr/bin/env python
"""
navdoon
"""

from __future__ import print_function

import os

try:
    import setuptools
    from setuptools import setup
except ImportError:
    setuptools = None
    from distutils.core import setup

try:
    import distutilazy.test
    import distutilazy.clean
except ImportError:
    distutilazy = None

from navdoon import (__title__, __summary__, __version__, __author__,
                     __license__)

classifiers = [
    "Development Status :: 4 - Beta", "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 2.7",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.2",
    "Programming Language :: Python :: 3.3",
    "Programming Language :: Python :: 3.4",
    "Programming Language :: Python :: 3.5",
    "Programming Language :: Python :: Implementation :: CPython",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Topic :: System :: Networking :: Monitoring"
]

long_description = __summary__
with open(os.path.join(os.path.dirname(__file__), "README.rst")) as fh:
    long_description = fh.read()

setup_params = dict(name=__title__,
                    packages=["navdoon", "navdoon.pystdlib", "navdoon.destination", "navdoon.utils"],
                    version=__version__,
                    description=__summary__,
                    long_description=long_description,
                    author=__author__,
                    url="https://github.com/farzadghanei/navdoon",
                    license=__license__,
                    classifiers=classifiers,
                    install_requires=["statsdmetrics>=0.3"])

if setuptools:
    setup_params["keywords"] = "statsd monitoring"
    setup_params["test_suite"] = "tests"
    setup_params["zip_safe"] = False
    setup_params["extras_require"] = dict(
        dev=["distutilazy>=0.4.1", "typing>=3.5.0.1", "coverage"]
    )
    setup_params["entry_points"] = dict(
        console_scripts=["navdoon=navdoon.app:main",]
    )
else:
    setup_params["scripts"] = ['bin/navdoon']


if distutilazy:
    setup_params["cmdclass"] = dict(test=distutilazy.test.run_tests,
                                    clean_pyc=distutilazy.clean.clean_pyc,
                                    clean=distutilazy.clean.clean_all)

if __name__ == "__main__":
    setup(**setup_params)

__all__ = ('setup_params', 'classifiers', 'long_description')
