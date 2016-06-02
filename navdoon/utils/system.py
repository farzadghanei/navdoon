"""
navdoon.utils.system
--------------------
System utilities and mixin classes
"""

import platform
from multiprocessing import cpu_count


PLATFORM_NAME = platform.system().strip().lower()


def available_cpus():
    try:
        cpus = cpu_count()
    except Exception:
        cpus = 1
    return cpus


def os_syslog_socket():
    syslog_addresses = dict(
        linux="/dev/log",
        darwin="/var/run/syslog",
        freebsd="/var/run/log"
    )
    return syslog_addresses.get(PLATFORM_NAME, None)
