"""
module defining main interfaces and implementations for managing responses
"""
import json, io
from abc import ABC, abstractmethod, abstractproperty
from typing import Mapping, List, IO, AnyStr
from collections import OrderedDict
from datetime import datetime
from copy import deepcopy

from http_status import Status
from urllib3 import HTTPResponse
import requests
from requests.utils import get_encoding_from_headers

__all__ = ["Method", "Resource", "SimpleResource"]

File = IO[AnyStr]

class Method:
    GET    = "GET"
    POST   = "POST"
    PUT    = "PUT"
    DELETE = "DELETE"
    OPTIONS= "OPTIONS"
    HEAD   = "HEAD"
    MKCOL  = "MKCOL"
    FIND   = "FIND"

class Resource(ABC, Method):
    """
    an abstract base class that generates different responses for a particular 
    resource path.
    """

    def __init__(self, version: int = 1, version_label: str = "HTTP/1.1"):
        self._ver = version
        self._verstr = version_label

    @property
    def version(self):
        """The HTTP version as understood by the ``urlllib3`` module (defaults to 1)"""
        return self._ver

    @property
    def version_string(self):
        """The HTTP version label to appear in a response's status line (e.g. "HTTP/1.1")"""
        return self._verstr

    @abstractmethod
    def get_response_to(self, method: str, status: int=200, datestr: str='now') -> HTTPResponse:
        """
        return an HTTP-compliant response, including the header.
        :param str  method:  the desired HTTP method (e.g. "GET")
        :param int  status:  the desired HTTP status code (default: 200)
        :param str datestr:  the value to set as the Date header field. If 'now' 
                             (default), it will be set to the current time; if None,
                             the Date field will not be included. 
        :return:  a (urllib3) HTTPResponse object corresponding to the inputs 
        """
        raise NotImplementedError()

    def get_requests_response_to(self, method: str, status: int = 200,
                                 datestr: str = 'now') -> requests.Response:
        """
        :param str method:  the desired HTTP method (e.g. "GET")
        :param int status:  the desired HTTP status code (default: 200)
        :param str datestr:  the value to set as the Date header field. If 'now' 
                             (default), it will be set to the current time; if None,
                             the Date field will not be included. 
        :return:  a (urllib3) HTTPResponse object corresponding to the inputs 
        """
        return to_requests_response(self.get_response_to(method, status, datestr))

    def send(self, fp: File, method: str = "GET", status: int = 200, datestr: str = 'now'):
        """
        :param file     fp:  an open file-like object to write the response to
        :param str  method:  the desired HTTP method (e.g. "GET")
        :param int  status:  the desired HTTP status code (default: 200)
        :param str datestr:  the value to set as the Date header field. If 'now' 
                             (default), it will be set to the current time; if None,
                             the Date field will not be included. 
        """
        pass

    def respond(self, method: str = "GET", status: int = 200) -> str:
        """
        return a formatted (newline-delimited) HTTP response
        """
        pass

class InMemoryResource(Resource):
    """
    A resource where the response is configured internally
    """

    def __init__(self, config: Mapping = None):
        super(InMemoryResource, self).__init__()
        if config is None:
            config = {}
        self._data = config
        self._mkbody = {
            'bytes': self._make_bytes_body,
            'text':  self._make_text_body,
            'json':  self._make_json_body
        }

    def get_response_to(self, method: str, status: int=200, datestr: str='now') -> HTTPResponse:
        hdrs = OrderedDict()
        if datestr:
            if datestr.lower() == 'now':
                datestr = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S %Z")
            hdrs['Date'] = datestr
        
        hdrs.update(self._data.get('headers', OrderedDict()))

        bymeth = self._data.get(method)
        if not bymeth:
            bymeth = self._data.get("def", {})

        hdrs.update(bymeth.get('headers', {}))

        bystat = bymeth.get(status)
        if not bystat:
            bystat = bymeth.get('def', {})
        hdrs.update(bystat.get('headers', {}))

        return self._make_resp(method, status, hdrs, bystat)

    def _make_resp(self, method: str, status: int, headers: Mapping, respcfg: Mapping):
        stat = Status(status)
        ct = headers.get("Content-Type")
        return HTTPResponse(self._make_body(method, status, respcfg, ct), 
                            headers, status, self.version, self.version_string, stat.name)

    def _make_body(self, method, status, respdata, contenttype: str=None):
        if method == "HEAD":
            return self._make_empty_body(method, status)

        if not contenttype:
            contenttype = "def"
        bdata = respdata.get('body', {})
        if bdata:
            if bdata.get(contenttype) is None and contenttype != "def":
                bdata = bdata.get("def")
            else:
                bdata = bdata.get(contenttype)
        if not bdata:
            return self._make_empty_body(method, status)

        btype = bdata.get('type', 'text')
        return self._mkbody.get(btype, self._make_bytes_body)(method, status, bdata)

    def _make_empty_body(self, method, status, *args):
        return io.BytesIO(b'')

    def _make_text_body(self, method, status, bodydata):
        body = bodydata.get('content', '')
        enc = bodydata.get('encoding', 'utf-8')
        if isinstance(body, str):
            try:
                body = body.encode(enc)
            except Exception as ex:
                raise ConfigError(f"Bad body encoding string for {method}/{status}")
        return io.BytesIO(body)

    def _make_bytes_body(self, method, status, bodydata):
        body = bodydata.get('content', '')
        if isinstance(body, str):
            enc = bodydata.get('encoding', 'utf-8')
            try:
                body = body.encode(enc)
            except Exception as ex:
                raise ConfigError(f"Bad body encoding string for {method}/{status}")
        return io.BytesIO(body)

    def _make_json_body(self, method, status, bodydata):
        return io.BytesIO(json.dumps(bodydata.get('content')).encode('utf-8'))

_simple_config = {
    "headers": OrderedDict([
        ("Server", "http-status-server"),
        ("Content-Type", "text/plain"),
    ])
}

def _merge_config(updates: Mapping, defconf: Mapping) -> Mapping:
    # knicked from oar-metadata (https://github.com/usnistgov/oar-metadata),
    # nistoar.base.config.merge_config()
    out = deepcopy(defconf)
    for key in updates:
        if isinstance(updates[key], Mapping) and \
           isinstance(out.get(key), Mapping):
            out[key] = _merge_config(updates[key], out[key])
        else:
            out[key] = updates[key]
    return out

def to_requests_response(response: HTTPResponse, url: str = '/') -> requests.Response:
    """
    convert requests.Response object.
    """
    # adapted from requests.adapters.HTTPAdapter.build_response()
    out = requests.Response()
    out.status_code = response.status
    out.encoding = get_encoding_from_headers(response.headers) or "utf-8"

    if isinstance(response._body, str):
        out.raw = io.BytesIO(response._body.encode(out.encoding))
    elif isinstance(response._body, bytes):
        out.raw = io.BytesIO(response._body)
    elif isinstance(response._fp, io.BytesIO):
        out.raw = io.BytesIO(response._fp.getvalue())
    elif response._fp:
        out.raw = response._fp
    else:
        out.raw = None
            
    out.reason = response.reason
    out.url = url

    return out
    

class SimpleResource(InMemoryResource):
    """
    A simple implementation of a resource that focuses primarily on returning a 
    response with the requested status.  

    It is possible to configure this class for specific headers and bodies (as with
    :py:class:`InMemoryResource`, but it is not required.  
    """

    def __init__(self, config: Mapping = None):
        if config is None:
            config = _simple_config
        else:
            config = _merge_config(config, _simple_config)

        super(SimpleResource, self).__init__(config)

