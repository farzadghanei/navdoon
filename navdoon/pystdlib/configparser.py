"""
navdoon.pystdlib.confirparser
-----------------------------
Abstract configparser/ConfigParser module from Python standard library
"""

try:
    from ConfigParser import *
except ImportError:
    from configparser import *
