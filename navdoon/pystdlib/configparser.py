"""
navdoon.pystdlib.confirparser
-----------------------------
Abstract configparser/ConfigParser module from Python standard library
"""

# type: ignore

try:
    from ConfigParser import *
except ImportError:
    from configparser import *
