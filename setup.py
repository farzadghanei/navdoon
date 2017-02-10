#!/usr/bin/env python
"""
navdoon
"""

from __future__ import print_function

import os
from setuptools import setup, find_packages

try:
    import distutilazy.test, distutilazy.clean  # type: ignore
except ImportError:
    distutilazy = None  # type: ignore


from navdoon import (__title__, __summary__, __version__, __author__,
                     __license__)

__all__ = ['setup_params', 'classifiers', 'long_description']  # type: ignore

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
    "Programming Language :: Python :: 3.6",
    "Programming Language :: Python :: Implementation :: CPython",
    "Programming Language :: Python :: Implementation :: PyPy",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Topic :: System :: Networking :: Monitoring"
]  # type: ignore

long_description = __summary__  # type: str
with open(os.path.join(os.path.dirname(__file__), "README.rst")) as fh:
    long_description = fh.read()

setup_params = dict(name=__title__,
                    packages=find_packages(),
                    version=__version__,
                    description=__summary__,
                    long_description=long_description,
                    author=__author__,
                    url="https://github.com/farzadghanei/navdoon",
                    license=__license__,
                    classifiers=classifiers,
                    install_requires=["statsdmetrics>=0.3"],
                    keywords="statsd monitoring",
                    test_suite="tests",
                    zip_safe=False,
                    extras_require=dict(
                        dev=["distutilazy>=0.4.2", "typing>=3.5.0.1", "coverage"]
                    ),
                    entry_points=dict(
                        console_scripts=["navdoon=navdoon.app:main", ]
                    ),
                    scripts=['bin/navdoon']
                    )  # type: ignore

if distutilazy:
    setup_params["cmdclass"] = dict(test=distutilazy.test.run_tests,
                                    clean_pyc=distutilazy.clean.clean_pyc,
                                    clean=distutilazy.clean.clean_all)

if __name__ == "__main__":
    setup(**setup_params)