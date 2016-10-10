*******
Navdoon
*******

.. image:: https://travis-ci.org/farzadghanei/navdoon.svg?branch=master
    :target: https://travis-ci.org/farzadghanei/navdoon

.. image:: https://codecov.io/github/farzadghanei/navdoon/coverage.svg?branch=master
    :target: https://codecov.io/github/farzadghanei/navdoon?branch=master

.. image:: https://ci.appveyor.com/api/projects/status/67gbsru6tp3tjxaq/branch/master?svg=true
    :target: https://ci.appveyor.com/project/farzadghanei/navdoon?branch=master


Powerful Statsd server, made easy.

Navdoon is a portable Statsd server with useful features to make it easy to
use, extend and integrate.

Features
--------
* Portable with few dependencies, easy to install on most platforms
* Support TCP, UDP
* Receive metrics from multiple addresses
* Flush to multiple Graphite backends
* Easy to integrate with custom programs
* Ability to reload the server without losing the metrics


Details
=======

* Navdoon uses collectors to receive Statsd metrics and recieves metrics over
  UDP (`--collect-udp`) and TCP (`--collect-tcp`),
  and accepts multiple collectors.

* The server saves/sends (flushes) the accumulated metrics every often
  (`--flus-interval`) to a persistent storage.
  `Carbon <https://pypi.python.org/pypi/carbon>`_ (from `Graphite <http://graphite.readthedocs.io/>`_ project)
  is a very common backend for Statsd servers. Navdoon accepts multiple Graphite addresses (`--flush-graphite`)
  so it can flush to multiple backends (all share the same interval).
  Metrics can be flushed to standard output (`--flush-stdout`) to pipe to another
  program, so it's easy to integrate with any custom backend.

* Logging can be helpful or can be wasteful, depending on the deployment and the usage of the application.
  Navdoon provides detailed configuration on logging, so you can chose what will be logged (`--log-level`)
  and how to log, send logs to syslog (`--log-syslog`), to a file (`--log-file`) or standard error
  (`--log-stderr`) to be piped to another program.

* While not claiming to be the fastest, good performance is considered in the design.
  Navdoon uses threads for each collector and flush backend.
  Future versions will offer improved performance as it was not a priority
  for the first releases.

* Server supports reloading (on receiving SIGHUP), keeping current state of the metrics and last flush time.
  So it's possible to change collectors, flush destinations, logging, etc. on the configuration file while
  the server is running, and then on sending a SIGHUP the server picks the new configuration.


Releases
========
* Latest released version is *0.2.0* (released on 2016-10-10)
* Previous released version was *0.1.1* (released on 2016-06-15)

See the CHANGELOG for more information about features provided by each release.



Requirements
------------
Navdoon is written in Python, so running from source or installing it as a package,
requires a Python runtime (version 2.7+, latest versions of Python 3 is recommended).

The `statsdmetrics <https://pypi.python.org/pypi/statsdmetrics>`_ Python module
is the only dependency to run navdoon.
However these Python modules are recommended on development/test environment:

* `distutilazy <https://pypi.python.org/pypi/distutilazy>`_ (>=0.4.2): helpful commands added to `setup.py` to run tests and clean temp files
* `typing <https://pypi.python.org/pypi/typing>`_ (>=3.5.0): standard type annotations for Python
* `coveage <https://pypi.python.org/pypi/coverage>`_: create test coverage reports


Running from source
-------------------
Before running from source, a few dependencies should be installed. Using a virtual
environment is suggested. (In this example we create a virtual environment
in the project source path, but you may chose a custom path like
~/.venvs/navdoon-py3)


.. code-block:: bash

    git clone https://github.com/farzadghanei/navdoon.git && cd navdoon
    python3 -m venv .navdoon-venv-py3 && source ./.navdoon-venv-py3/bin/activate
    pip install -r requirements.txt && python3 bin/navdoon_src


.. note:: Python 3.3+ standard library comes with `venv` module.
            For older versions you can use
            `virtualenv <https://pypi.python.org/pypi/virtualenv>`_.


Or you may skip installing and sourcing the virtual environment and install the (few)
dependencies on your system.



Install
-------
Navdoon can be installed from `pypi <https://pypi.python.org>`_ using `pip`.


.. code-block:: bash

    pip install navdoon


You can install from the source by running the `setup.py` script provided.


.. code-block:: bash

    python setup.py install


.. note:: If you're installing navdoon to a system path, you might need to
            run the installation with `sudo` or under a privileged user.


License
-------

Navdoon is released under the terms of the
`Apache 2.0 license <http://www.apache.org/licenses/LICENSE-2.0>`_.
