*******
Navdoon
*******

.. image:: https://travis-ci.org/farzadghanei/navdoon.svg?branch=master
    :target: https://travis-ci.org/farzadghanei/navdoon

.. image:: https://codecov.io/github/farzadghanei/navdoon/coverage.svg?branch=master
    :target: https://codecov.io/github/farzadghanei/navdoon?branch=master

.. image:: https://ci.appveyor.com/api/projects/status/67gbsru6tp3tjxaq/branch/master?svg=true
    :target: https://ci.appveyor.com/api/projects/status/67gbsru6tp3tjxaq/branch/master?svg=true


Powerful Statsd server, made easy.

Navdoon is a portable Statsd server with useful features to make it easy to
use, extend and integrate.

While not claiming to be the fastest, performance is one of the features considered
in the design (more on this later).

Requirements
-------------
Navdoon is written in Python, so running from source or installing it as a package,
requires a Python runtime (version 2.7+, latest versions of Python 3 is recommended).


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


.. note:: Python 3.3+ standard library comes with `venv` module,
        for older versions you can install
        `virtualenv <https://pypi.python.org/pypi/virtualenv>`_.


Or you may skip installing and sourcing the virtual environment and install the (few)
dependencies on your system.




Install
-------
When installing from source, dependencies should also be installed.


License
-------

Navdoon is released under the terms of the
`Apache 2.0 license <http://www.apache.org/licenses/LICENSE-2.0>`_.
