"""
module defining main interfaces and implementations for managing responses
"""
import json, io
from abc import ABC, abstractmethod, abstractproperty
from typing import Mapping, List, IO, AnyStr, Union
from collections import OrderedDict, ChainMap
from datetime import datetime
from copy import deepcopy

from http_status import Status
from urllib3 import HTTPResponse, HTTPHeaderDict
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
    an abstract base class that generates various responses for a particular 
    resource path.

    A ``Resource`` instance is a stand-in for a URL-accessible web resource.  Through
    its interface, one can retrieve a response for a particular request method and 
    desired response status.  The response can come in various forms:  a 
    ``urllib3.HTTPResponse``, a ``requests.Response``, or a raw HTTP message.
    
    
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

    def request(self, method: str, status: int = 200,
                datestr: str = 'now') -> requests.Response:
        """
        return an HTTP response of the type returned by the ``requests`` module.
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
        Write a fully formatted HTTP response to a given file.

        This function will detect whether the stream is expecting bytes or strings and 
        write accordingly.  Of course, to be HTTP compliant, the output stream must be a 
        a byte stream; however, a text stream can be helpful for debugging.

        :param file     fp:  an open file-like object to write the response to
        :param str  method:  the desired HTTP method (e.g. "GET")
        :param int  status:  the desired HTTP status code (default: 200)
        :param str datestr:  the value to set as the Date header field. If 'now' 
                             (default), it will be set to the current time; if None,
                             the Date field will not be included. 
        """
        send_response(fp, self.get_response_to(method, status, datestr))

    def respond(self, method: str = "GET", status: int = 200, datestr: str = 'now') -> str:
        """
        return a formatted (newline-delimited) HTTP response
        """
        out = io.StringIO()
        self.send(out, method, status, datestr)
        return out.getvalue()

def send_response(fp: File, resp: HTTPResponse):
    """
    Write a given response object to file stream as a fully formatted HTTP response.

    This function will detect whether the stream is expecting bytes or strings and 
    write accordingly.  Of course, to be HTTP compliant, the output stream must be a 
    a byte stream; however, a text stream can be helpful for debugging.
    """
    def no_encode(b):
        return b
    def do_encode(s):
        return s.encode('utf-8')
    encode = no_encode if isinstance(fp, io.TextIOBase) else do_encode
    def writeln(b):
        fp.write(encode(b))
        fp.write(encode("\r\n"))

    writeln(f"{resp.version_string} {resp.status}")
    for nm, val in resp.headers.items():
        if isinstance(val, (list, tuple)):
            for v in val:
                writeln(f"{nm}: {v}")
        else:
            writeln(f"{nm}: {val}")
    writeln('')

    data = resp.data
    if isinstance(fp, io.TextIOBase):
        enc = get_encoding_from_headers(resp.headers) or 'utf-8'
        data = data.decode(enc)
    fp.write(data)

    

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
            # first pick up headers from default to method
            bystat = self._data.get('def', {}).get(status)
            if bystat:
                hdrs.update(bystat.get('headers', {}))

            # now pick up headers from default to status
            bystat = bymeth.get('def', {})
        hdrs.update(bystat.get('headers', {}))

        return self._make_resp(method, status, hdrs, bystat)

    def _make_resp(self, method: str, status: int, headers: Mapping, respcfg: Mapping):
        # make an HTTPHeaderDict to properly deal with multiple values
        hdrs = HTTPHeaderDict()
        for fld, val in headers.items():
            if isinstance(val, (list, tuple)):
                for v in val:
                    hdrs.add(fld, v)
            else:
                hdrs.add(fld, val)

        stat = Status(status)
        ct = headers.get("Content-Type")
        return HTTPResponse(self._make_body(method, status, respcfg, ct), 
                            hdrs, status, self.version, self.version_string, stat.name)

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

class ConfigurableResource(InMemoryResource):
    """
    a Resource whose responses can be configured after instantiation.  
    """

    def __init__(self, config: Mapping = None):
        if config is None:
            config = _simple_config
        else:
            config = _merge_config(config, _simple_config)
        cfg = ChainMap(OrderedDict(), config)
        super(ConfigurableResource, self).__init__(cfg)

    def set_header_for(self, header_name: str, val: Union[str,List[str]],
                       method: str = None, status: Union[int,None] = None):
        """
        set a header that should be included in particular responses.  If this header 
        is already set, the new value(s) will replace it until :py:meth:`reset` is called.

        :param str   header_name:  the name of the header item to set
        :param str|list(str) val:  the value to give the header.  A list of 
                                   values can be given
        :param str        method:  the HTTP request method to associate it with;
                                   it will only be returned when this method is 
                                   requested.  If not provided, it will be returned 
                                   for all methods.
        :param int        status:  the HTTP status to associate it with; it will only
                                   be returned when requesting a this particular status
                                   value.  If not provided, it will be returned regardless
                                   the requested status (see also ``method``)
        """
        if isinstance(val, list):
            if any(not isinstance(v, str) for v in val):
                raise ValueError("set_header_for: val not a list of str: "+str(val))
        elif not isinstance(val, str):
            raise ValueError("set_header_for: val not a str: "+str(val))

        hdrs = self._get_headers_for(method, status)
        hdrs[header_name] = val

    def _get_headers_for(self, method, status):
        # this retrieves header nodes for the purpose of setting new headers
        if method:
            method = method.upper()
        if not method and not status:
            # applies to all methods and statuses
            out = self._get_cfg_for_upd("headers")
        elif method and not status:
            # applies to all status for given method
            meth = self._get_cfg_for_upd(method)
            out = meth.setdefault("headers", OrderedDict())
        else:
            # status is not None
            if not method:
                # applies to default method
                method = "def"
            meth = self._get_cfg_for_upd(method)
            stat = meth.setdefault(status, OrderedDict())
            out = stat.setdefault("headers", OrderedDict())
            
        return out

    def _get_cfg_for_upd(self, key):
        out = self._data.maps[0].get(key)
        if not out:
            out = deepcopy(self._data.maps[1].get(key))
            if not out:
                out = OrderedDict()
            self._data[key] = out
        return out

    def set_headers_for(self, headers: Mapping[str, Union[str, List[str]]],
                        method: str = None, status: Union[int, None] = None):
        """
        set a header that should be included in particular responses.  If this header 
        is already set, the new value(s) will replace it until :py:meth:`reset` is called.

        :param dict headers:  the name of the header item to set
        :param str   method:  the HTTP request method to associate it with;
                              it will only be returned when this method is 
                              requested.  If not provided, it will be returned 
                              for all methods.
        :param int   status:  the HTTP status to associate it with; it will only
                              be returned when requesting a this particular status
                              value.  If not provided, it will be returned regardless
                              the requested status (see also ``method``)
        """
        def _bad_val(name, val):
            if isinstance(val, list):
                if any(not isinstance(v, str) for v in val):
                    return name
            elif not isinstance(val, str):
                return name
            return None
        bad = [n for n in [_bad_val(nm, v) for nm, v in headers.items()] if n]
        if bad:
            raise ValueError("set_headers_for: headers contains fields with bad values: " +
                             ", ".join(bad))

        hdrs = self._get_headers_for(method, status)
        hdrs.update(headers)

    def add_header_for(self, header_name: str, val: Union[str,List[str]],
                       method: str = None, status: Union[int,None] = None):
        """
        Add additional values for a particular header item to be returned.  

        This is like :py:meth:`set_header_for` except that it adds additional values 
        to those already set.  

        :param str   header_name:  the name of the header item to set
        :param str|list(str) val:  the value (or list of values) to add to the exiting 
                                   values (if any) for the header item.  
        :param str        method:  the HTTP request method to associate the header value
                                   with; they will only be returned when this method is 
                                   requested.  If not provided, they will be returned 
                                   for all methods.  
        :param int        status:  the HTTP status to associate it with; it will only
                                   be returned when requesting a this particular status
                                   value.  If not provided, tey will be returned regardless
                                   the requested status (see also ``method``)
        """
        if isinstance(val, list):
            if any(not isinstance(v, str) for v in val):
                raise ValueError("set_header_for: val not a list of str: "+str(val))
        elif not isinstance(val, str):
            raise ValueError("set_header_for: val not a str: "+str(val))

        hdrs = self._get_headers_for(method, status)
        if isinstance(hdrs.get(header_name), str):
            hdrs[header_name] = [ hdrs[header_name] ]
        hdrs.setdefault(header_name, [])
        if isinstance(val, str):
            hdrs[header_name].append(val)
        else:
            hdrs[header_name].extend(val)

    def set_header(self, header_name: str, val: Union[str,List[str]]):
        """
        set a header item to appear in all responses (regardless of method or requested 
        status).

        :param str   header_name:  the name of the header item to set
        :param str|list(str) val:  the value to give the header.  A list of 
                                   values can be given
        """
        self.set_header_for(header_name, val)

    def set_headers(self, headers: Mapping[str, Union[str, List[str]]]):
        """
        set a header item to appear in all responses (regardless of method or requested 
        status).

        :param str   header_name:  the name of the header item to set
        :param str|list(str) val:  the value to give the header.  A list of 
                                   values can be given
        """
        self.set_headers_for(headers)

    def add_header(self, header_name: str, val: Union[str,List[str]]):
        """
        Add additional values for a particular header item to be returned.  

        This is like :py:meth:`add_header_for` except that it will be returned for 
        all method and status requests.

        :param str   header_name:  the name of the header item to set
        :param str|list(str) val:  the value (or list of values) to add to the exiting 
                                   values (if any) for the header item.  
        """
        self.add_header_for(header_name, val)

    def set_json_body_for(self, data, method: str=None, status: int=None,
                          content_types: List[str] = ["def", "application/json"]):
        """
        set the data that should be returned as JSON in the response body when requesting a 
        particular method and status.  
        
        :param       data:  JSON-serializable data to return in the body
        :param str method:  the HTTP request method to associate the header value
                            with; they will only be returned when this method is 
                            requested.  If not provided, they will be returned 
                            for all methods.  
        :param int status:  the HTTP status to associate it with; it will only
                            be returned when requesting a this particular status
                            value.  If not provided, tey will be returned regardless
                            the requested status (see also ``method``)
        :param list(str) content_types:  the content type values to associate this 
                            this with; this body will only be returned when the response
                            includes a "Content-Type" header whose value matches one
                            of these values.  Include the special value, "def", to return
                            this body when there is no "Content-Type" header item or it 
                            otherwise doesn't match any currently configured ones.  
        """
        json.dumps(data)  # may throw ValueError
        bdata = {"type": "json", "content": data}
        self._set_body(bdata, method, status, content_types)

    def _set_body(self, bodycfg, method, status, content_types):
        if isinstance(content_types, str):
            content_types = [ content_types ]

        bodies = self._get_bodies_for(method, status)
        for ct in content_types:
            bodies[ct] = bodycfg

    def _get_bodies_for(self, method: str, status: Union[int,None]):
        if method and method != "def":
            method = method.upper()
        else:
            method = "def"
        meth = self._data.get(method, OrderedDict())
        self._data[method] = meth
        if not status:
            status = "def"
        stat = meth.get(status, OrderedDict())
        meth[status] = stat

        out = stat.get("body", OrderedDict())
        stat["body"] = out
        return out

    def set_text_body_for(self, text: str, method: str=None, status: int=None,
                          content_types: List[str] = ["text/plain"]):
        """
        set the text that should be returned in the response body when requesting a 
        particular method and status.  
        
        :param       data:  JSON-serializable data to return in the body
        :param str method:  the HTTP request method to associate the header value
                            with; they will only be returned when this method is 
                            requested.  If not provided, they will be returned 
                            for all methods.  
        :param int status:  the HTTP status to associate it with; it will only
                            be returned when requesting a this particular status
                            value.  If not provided, tey will be returned regardless
                            the requested status (see also ``method``)
        :param list(str) content_types:  the content type values to associate this 
                            this with; this body will only be returned when the response
                            includes a "Content-Type" header whose value matches one
                            of these values.  Include the special value, "def", to return
                            this body when there is no "Content-Type" header item or it 
                            otherwise doesn't match any currently configured ones.  
        """
        if not isinstance(data, str):
            raise ValueError("set_text_body: data: not a str: "+str(data))
        bdata = {"type": "text", "content": data}
        self._set_body(bdata, method, status, content_types)

    def set_bytes_body_for(self, data: bytes, method: str=None, status: int=None,
                           content_types: List[str] = ["application/octet-stream"]):
        """
        set the text that should be returned in the response body when requesting a 
        particular method and status.  
        
        :param       data:  JSON-serializable data to return in the body
        :param str method:  the HTTP request method to associate the header value
                            with; they will only be returned when this method is 
                            requested.  If not provided, they will be returned 
                            for all methods.  
        :param int status:  the HTTP status to associate it with; it will only
                            be returned when requesting a this particular status
                            value.  If not provided, tey will be returned regardless
                            the requested status (see also ``method``)
        :param list(str) content_types:  the content type values to associate this 
                            this with; this body will only be returned when the response
                            includes a "Content-Type" header whose value matches one
                            of these values.  Include the special value, "def", to return
                            this body when there is no "Content-Type" header item or it 
                            otherwise doesn't match any currently configured ones.  
        """
        if not isinstance(data, bytes):
            raise ValueError("set_text_body: data: not bytes: "+str(data))
        bdata = {"type": "bytes", "content": data}
        self._set_body(bdata, method, status, content_types)

    def reset(self):
        """
        Revert the behavior configuration back to what it was at construction time.
        """
        if hasattr(self._data, 'maps'):
            self._data.maps[0] = OrderedDict()

    
        
        
