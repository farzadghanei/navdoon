"""
navdoon.pystdlib.queue
----------------------
Abstract queue/Queue module from Python standard library
"""

try:
    from Queue import *
except ImportError:
    from queue import *
