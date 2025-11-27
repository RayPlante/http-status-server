# http-status-server

a test server for delivering specific HTTP status responses (e.g. a replacement for
httpstatus.us), implemented in Python.

This software generates HTTP service responses with highly specified detail for the
purposes of testing service clients.  It supports several execution modes:

  * a stand-alone web server (e.g. running on localhost)
  * an WSGI application
  * a command-line tool
  * a Python package (allowing for injection into [mock objects](https://docs.python.org/3/library/unittest.mock.html) 

## Warning and Disclaimer

This package is currently in early development and is not recommended for deployment as a
publicly accessible server.  

## LICENSE

Copyright (c) 2025, Raymond L. Plante (raydangerplante@gmail.com)

This code is covered by the BSD 3-Clause Licesnse; see [LICENSE](LICENSE) for details.  

