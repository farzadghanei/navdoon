*****************
Navdoon Changelog
*****************

0.2.0
-----
Released on 2016-10-10

* Multi-threaded TCP collectors
* Flush to backend is done in consistent threads started with the server
* Server supports reloading on SIGHUP (re-read the config file, restart collectors
  and reconnect to backends).
* Improve handling of incomplete request lines over TCP
* Fix issue with setting SIGHUP handler when not available
* Fix config parser depreciation warnings
* Fix unittest depreciation warnings
* Fix ResourceWarning thrown by Python 3 for sockets not closed explicitly
* Update required distutilazy version to 0.4.2

0.1.1
-----
Released on 2016-06-15

* Fix issue with parsing config file overriding the defaults, requiring all directive to be present on
  the configuration file.
* Fix issue about missing log handler in tests
* Better support for Windows platform
