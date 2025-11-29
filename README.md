# http-status-server

a test server for delivering specific HTTP status responses (e.g. a replacement for
httpstatus.us), implemented in Python.

This software generates HTTP service responses with highly specified detail for the
purposes of testing service clients.  It supports several execution modes:

  * a stand-alone web server (e.g. running on localhost)
  * an WSGI application
  * a command-line tool
  * a Python package (allowing for injection into [mock objects](https://docs.python.org/3/library/unittest.mock.html))

## Installing

At this time, this package can only be installed from source.

To obtain the source repository, type:

```
git clone https://github.com/RayPlante/http-status-server
```

To install, change into the source directory, ``http-status-server``, and type:

```
python -m pip install .
```

## Using This Package

### Mocking ``requests`` Responses

_editing in progress_

### Mocking ``urllib3`` Responses

_editing in progress_

### Running as a Test Server

_editing in progress_

## Developing

### Set-up

Contributions can be made via pull requests to the
[http-statu-server GitHub repo](https://github.com/RayPlante/http-status-server).  To
obtain the repository for development, type:

```
git clone https://github.com/RayPlante/http-status-server
```

For development, it is recommended that you set up and activate a Python virtual 
environment (e.g. [venv](https://docs.python.org/3/library/venv.html)).  Once activated,
you can install the development dependencies:

```
python -m pip install setuptools
python -m pip install -r requirements.txt
```

This repo uses [setuptools](https://setuptools.pypa.io/en/latest/index.html) as its
backend build system.  It is helpful for development to install the software in "editable
mode":

```
python -m pip install --editable .
```

### Testing

Running all tests can be done most easily via the provided ``testall.sh`` script:
```
./testall.sh
```

The recommended way to run just the unit tests is to type:
```
python -m unittest discover -s tests
```

Any individual unit test file can be run by itself, for example:
```
python tests/http_status_server/test_response.py
```

## Warning and Disclaimer

This package is currently in early development (pre v1.0.0) and is not recommended for 
deployment as apublicly accessible server.

See the usual disclaimer statement in the last paragraph in [LICENSE](LICENSE) protecting
the authors and contributors from liability.

## LICENSE

Copyright (c) 2025, Raymond L. Plante (raydangerplante@gmail.com)

This code is covered by the BSD 3-Clause Licesnse; see [LICENSE](LICENSE) for details.  

