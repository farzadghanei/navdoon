"""
navdoon.pystdlib.typing
----------------------
Type hints from Python standard library. This is to remove requirements for Typing module to be available
on production.
"""
from __future__ import absolute_import

try:
    from typing import List, Dict, Tuple, AnyStr, IO, Any, Sequence, Set, Union, Callable, Optional, Mapping
except ImportError:
    List, Dict, Tuple, AnyStr, Any, IO, Sequence = None, None, None, None, None, None, None  # type: ignore
    Mapping, Set, Union, Callable, Optional = None, None, None, None, None  # type: ignore
