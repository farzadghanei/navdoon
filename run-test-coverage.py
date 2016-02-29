#!/usr/bin/env python
from __future__ import print_function
import platform
import subprocess
import sys
import os

python_version = platform.python_version_tuple()[:2]
is_py32 = python_version == (3, 2)
no_coverage = os.getenv('NO_COVERAGE', '')

if __name__ == '__main__':
    if is_py32:
        print("coverage.py does not support Python 3.2.", file=sys.stderr)
        print("Running tests without coverage ...", file=sys.stderr)
        subprocess.call("python setup.py test", shell=True)
    elif no_coverage != '':
        print("Running tests without coverage ...", file=sys.stderr)
        subprocess.call("python setup.py test", shell=True)
    else:
        subprocess.call("coverage run setup.py test", shell=True)
