import unittest, json, io
from collections import ChainMap
from typing import Mapping

import urllib3, requests

from http_status_server.response import SimpleResource, ConfigurableResource

bodycfg = {
    "def": {
        "type": "text",
        "content": b"it's default"
    },
    "text/json": {
        "type": "json",
        "content": { "a": 1, "b": 2 }
    },
    "application/octet-stream": {
        "type": "bytes",
        "content": b"it's bytes"
    },
    "text/plain": {
        "type": "text",
        "content": "it's text"
    }
}

class TestSimpleResource(unittest.TestCase):

    def setUp(self):
        self.res = SimpleResource()

    def test_ctor(self):
        self.assertEqual(self.res.version, 1)
        self.assertEqual(self.res.version_string, "HTTP/1.1")
        self.assertTrue(self.res._data)
        self.assertEqual(self.res._data.get("headers", {}).get("Server"),
                         "http-status-server")
        self.assertEqual(self.res._data.get("headers", {}).get("Content-Type"),
                         "text/plain")

    def test_make_empty_body(self):
        self.assertTrue(isinstance(self.res._make_empty_body("GET", 200, {}), io.BytesIO))
        self.assertEqual(self.res._make_empty_body("GET", 200).getvalue(), b'')
        self.assertEqual(self.res._make_empty_body("PUT", 500).getvalue(), b'')
        self.assertEqual(self.res._make_empty_body(None, 0).getvalue(), b'')

    def test_make_text_body(self):
        self.assertTrue(isinstance(self.res._make_text_body("GET", 200, {}), io.BytesIO))
        self.assertEqual(self.res._make_text_body("GET", 200, {}).getvalue(), b'')
        bcfg = { 'content': 'goob' }
        self.assertEqual(self.res._make_text_body("GET", 200, bcfg).getvalue(), b'goob')
        bcfg = { 'content': b'goob' } 
        self.assertEqual(self.res._make_text_body("GET", 200, bcfg).getvalue(), b'goob')
        bcfg = { 'content': 'goob'.encode('utf-16'), 'encoding': 'utf-16' } 
        self.assertEqual(self.res._make_text_body("GET", 200, bcfg).getvalue(),
                         'goob'.encode('utf-16'))

    def test_make_bytes_body(self):
        self.assertTrue(isinstance(self.res._make_bytes_body("GET", 200, {}), io.BytesIO))
        self.assertEqual(self.res._make_bytes_body("GET", 200, {}).getvalue(), b'')
        bcfg = { 'content': b'goob' }
        self.assertEqual(self.res._make_bytes_body("PUT", 500, bcfg).getvalue(), b'goob')
        bcfg = { 'content': 'goob' } 
        self.assertEqual(self.res._make_bytes_body("GET", 200, bcfg).getvalue(), b'goob')
        bcfg = { 'content': 'goob', 'encoding': 'utf-16' } 
        self.assertEqual(self.res._make_bytes_body("GET", 200, bcfg).getvalue().
                                                                     decode('utf-16'), 'goob')

    def test_make_json_body(self):
        self.assertTrue(isinstance(self.res._make_json_body("GET", 200, {}), io.BytesIO))
        self.assertEqual(self.res._make_json_body("GET", 200, {}).getvalue(), b'null')
        self.assertEqual(self.res._make_json_body("GET", 200, {"content": None}).getvalue(),
                         b'null')
        self.assertEqual(self.res._make_json_body("GET", 200, {"content": 3}).getvalue(), b'3')
        self.assertEqual(self.res._make_json_body("GET", 200, {"content": "goob"}).getvalue(),
                         b'"goob"')
        self.assertEqual(self.res._make_json_body("GET", 200, {"content": [1, 3]}).getvalue(),
                         b'[1, 3]')

    def test_make_body(self):
        cfg = { "body": bodycfg }
        self.assertEqual(self.res._make_body("HEAD", 202, cfg).getvalue(), b'')
        self.assertEqual(self.res._make_body("GET", 200, cfg).getvalue(), b"it's default")
        self.assertEqual(self.res._make_body("PUT", 400, cfg, "text/plain").getvalue(),
                         b"it's text")
        self.assertEqual(self.res._make_body("GOOB", 405, cfg, "application/octet-stream").
                                                                                    getvalue(),
                         b"it's bytes")
        self.assertEqual(self.res._make_body("POST", 500, cfg, "application/json").getvalue(),
                         b"it's default")
        self.assertEqual(self.res._make_body("PUT", 400, cfg, "text/json").getvalue(),
                         b'{"a": 1, "b": 2}')
        self.assertEqual(self.res._make_body("GET", 200, {"body": {}}).getvalue(), b'')
        self.assertEqual(self.res._make_body("GET", 200, {"body": {"def":{}}}).getvalue(), b'')
        
    def test_get_response_to(self):
        resp = self.res.get_response_to("GET", 200)
        self.assertTrue(isinstance(resp, urllib3.HTTPResponse))
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers.get("Content-Type"), "text/plain")
        self.assertEqual(resp.headers.get("Server"), "http-status-server")
        self.assertEqual(resp.data, b'')

        resp = self.res.get_response_to("HEAD", 404)
        self.assertEqual(resp.status, 404)
        self.assertEqual(resp.headers.get("Content-Type"), "text/plain")
        self.assertEqual(resp.headers.get("Server"), "http-status-server")
        self.assertEqual(resp.data, b'')

    def test_get_response_to_with_body(self):
        cfg = {
            "def": {
                "headers": {
                    "X-HTTP-Status-Server": "true"
                },
                "def": {
                    "body": bodycfg
                }
            },
            "POST": {
                "headers": {
                    "X-HTTP-Status-Server": "false"
                },
                200: {
                    "headers": {
                        "Cache-Control": "max-age=1",
                        "Content-Type": "text/json"
                    },
                    "body": {
                        "text/json": { "type": "json", "content": { "id": 1 } }
                    }
                },
                400: {
                    "headers": {
                        "Cache-Control": "max-age=10"
                    },
                    "body": {
                        "def": { "type": "text", "content": "Ouch!" }
                    }
                }
            },
            "GOOB": {
                "def": {
                    "body": { "def": { "type": "text", "content": "Goob!" } }
                }
            }
        }
        self.res = SimpleResource(cfg)

        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers.get("Server"), "http-status-server")
        self.assertEqual(resp.headers.get("X-HTTP-Status-Server"), "true")
        self.assertIn('Date', resp.headers)
        self.assertNotIn('Cache-Control', resp.headers)
        self.assertEqual(resp.headers.get("Content-Type"), "text/plain")
        self.assertEqual(resp.data, b"it's text")

        resp = self.res.get_response_to("POST", 400)
        self.assertEqual(resp.status, 400)
        self.assertEqual(resp.headers.get("Server"), "http-status-server")
        self.assertEqual(resp.headers.get("X-HTTP-Status-Server"), "false")
        self.assertEqual(resp.headers.get("Cache-Control"), "max-age=10")
        self.assertIn('Date', resp.headers)
        self.assertEqual(resp.headers.get("Content-Type"), "text/plain")
        self.assertEqual(resp.data, b"Ouch!")

        resp = self.res.get_response_to("POST", 200, datestr=None)
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers.get("Server"), "http-status-server")
        self.assertEqual(resp.headers.get("X-HTTP-Status-Server"), "false")
        self.assertEqual(resp.headers.get("Cache-Control"), "max-age=1")
        self.assertNotIn('Date', resp.headers)
        self.assertEqual(resp.headers.get("Content-Type"), "text/json")
        self.assertEqual(resp.data, b'{"id": 1}')
        self.assertEqual(resp.json(), {"id": 1})

        resp = self.res.get_response_to("GOOB", 501)
        self.assertEqual(resp.status, 501)
        self.assertEqual(resp.headers.get("Server"), "http-status-server")
        self.assertIn('Date', resp.headers)
        self.assertNotIn('Cache-Control', resp.headers)
        self.assertNotIn('X-HTTP-Status-Server', resp.headers)
        self.assertEqual(resp.headers.get("Content-Type"), "text/plain")
        self.assertEqual(resp.data, b"Goob!")

    def test_request(self):
        cfg = { "def": { "def": { "body": bodycfg } } }
        self.res = SimpleResource(cfg)
        
        resp = self.res.request("GET", 200)
        self.assertTrue(isinstance(resp, requests.Response))
        self.assertEqual(resp.content, b"it's text")
        self.assertEqual(resp.text, "it's text")

        cfg.setdefault('headers', {})['Content-Type'] = "text/json"
        self.res = SimpleResource(cfg)
        resp = self.res.request("GET", 200)
        self.assertEqual(resp.text, '{"a": 1, "b": 2}')
        self.assertEqual(resp.json(), { "a": 1, "b": 2 })

    def test_respond(self):
        resp = self.res.respond(self.res.GET, 202, "Today")
        self.assertEqual(resp, _respond_str)

        cfg = { "def": { "def": { "body": bodycfg } } }
        self.res = SimpleResource(cfg)
        resp = self.res.respond(self.res.GET, 202, "Today")
        text = _respond_str + "it's text"
        self.assertEqual(resp, text)

    def test_send(self):
        dest = io.BytesIO()
        self.res.send(dest, self.res.GET, 202, "Today")
        self.assertEqual(dest.getvalue(), _respond_str.encode('utf-8'))

        cfg = { "def": { "def": { "body": bodycfg } } }
        self.res = SimpleResource(cfg)
        dest = io.BytesIO()
        self.res.send(dest, self.res.GET, 202, "Today")
        text = _respond_str + "it's text"
        self.assertEqual(dest.getvalue(), text.encode('utf-8'))
        
_respond_str = """HTTP/1.1 202\r
Date: Today\r
Server: http-status-server\r
Content-Type: text/plain\r
\r
"""

class TestConfigurableResource(unittest.TestCase):

    def setUp(self):
        cfg = {
            "headers": { "TestResource": "true" }
        }
        self.res = ConfigurableResource(cfg)

    def test_ctor(self):
        self.assertTrue(isinstance(self.res._data, ChainMap))
        self.assertTrue(isinstance(self.res._data.get("headers"), Mapping))
        self.assertEqual(self.res._data['headers'].get("TestResource"), "true")
        self.assertEqual(self.res._data['headers'].get("Server"), "http-status-server")
        self.assertEqual(self.res._data['headers'].get("Content-Type"), "text/plain")

    def test_get_headers_for(self):
        self.assertIsNone(self.res._data.maps[0].get("headers"))
        hdrs = self.res._get_headers_for(None, None)
        self.assertEqual(hdrs.get("TestResource"), "true")
        self.assertEqual(hdrs.get("Server"), "http-status-server")
        self.assertEqual(hdrs.get("Content-Type"), "text/plain")
        self.assertEqual(self.res._data.maps[0].get("headers"), hdrs)

        self.assertIsNone(self.res._data.maps[0].get("GOOB"))
        self.assertEqual(self.res._get_headers_for("GOOB", None), {})
        self.assertEqual(self.res._data.maps[0]["GOOB"].get('headers'), {})

        self.res._data.maps[1].setdefault("GET", {}).setdefault(200, {})['headers'] = {'a':'1'}
        self.assertEqual(self.res._get_headers_for("GET", 200), {'a':'1'})
        self.assertEqual(self.res._get_headers_for("GET", 202), {})
        self.assertEqual(self.res._data.maps[0].get("GET").get(202), {'headers': {}})

    def test_get_bodies_for(self):
        self.assertIsNone(self.res._data.maps[0].get("def"))
        bods = self.res._get_bodies_for(None, None)

        self.assertEqual(bods, {})
        self.assertEqual(self.res._data.maps[0].get("def", {}).get("def"), {"body": {}})

        bods = self.res._get_bodies_for(None, 400)
        self.assertEqual(bods, {})
        self.assertEqual(self.res._data.maps[0].get("def",{}).get(400), {"body": {}})
        
        bods = self.res._get_bodies_for("GET", None)
        self.assertEqual(bods, {})
        self.assertEqual(self.res._data.maps[0].get("GET"), {"def": {"body": {}}})
        
        bods = self.res._get_bodies_for("GET", 500)
        self.assertEqual(bods, {})
        self.assertEqual(self.res._data.maps[0].get("GET").get(500), {"body": {}})

    def test_set_headers(self):
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.headers.get("Server"), "http-status-server")
        self.assertEqual(resp.headers.get("Content-Type"), "text/plain")
        self.assertIsNone(resp.headers.get("X-Test"))

        self.res.set_headers({"Server": "mystery", "X-Test": "red"})
        self.res.set_header_for("Content-Type", "text/json", status=404)
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.headers.get("Server"), "mystery")
        self.assertEqual(resp.headers.get("Content-Type"), "text/plain")
        self.assertEqual(resp.headers.get("X-Test"), "red")
        resp = self.res.get_response_to("GET", 404)
        self.assertEqual(resp.headers.get("Server"), "mystery")
        self.assertEqual(resp.headers.get("Content-Type"), "text/json")
        self.assertEqual(resp.headers.get("X-Test"), "red")

        self.res.add_header_for("X-Test", ["yellow", "green"])
        self.res.add_header_for("X-Test", ["yellow", "green"], "POST", 500)
        self.res.add_header_for("X-Req", "true", "POST")
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.headers.get("Server"), "mystery")
        self.assertEqual(resp.headers.get("Content-Type"), "text/plain")
        self.assertEqual(resp.headers.get("X-Test"), "red, yellow, green")
        resp = self.res.get_response_to("POST", 404)
        self.assertEqual(resp.headers.get("Server"), "mystery")
        self.assertEqual(resp.headers.get("Content-Type"), "text/json")
        self.assertEqual(resp.headers.get("X-Test"), "red, yellow, green")
        self.assertEqual(resp.headers.get("X-Req"), "true")
        resp = self.res.get_response_to("POST", 500)
        self.assertEqual(resp.headers.get("Server"), "mystery")
        self.assertEqual(resp.headers.get("Content-Type"), "text/plain")
        self.assertEqual(resp.headers.get("X-Test"), "yellow, green")
        self.assertEqual(resp.headers.get("X-Req"), "true")

        self.res.reset()
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.headers.get("Server"), "http-status-server")
        self.assertEqual(resp.headers.get("Content-Type"), "text/plain")
        self.assertIsNone(resp.headers.get("X-Test"))
        
    def test_set_text_body(self):
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("GET", 400)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("PUT", 400)
        self.assertEqual(resp.data, b'')

        self.res.set_text_body_for('"Ready!"', "GET", 200, ["text/plain", "text/json"])
        self.res.set_text_body_for('Error!')
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.data, b'"Ready!"')
        resp = self.res.get_response_to("GET", 400)
        self.assertEqual(resp.data, b'Error!')
        resp = self.res.get_response_to("PUT", 400)
        self.assertEqual(resp.data, b'Error!')

        self.res.set_header_for("Content-Type", "application/json", "GET", 200)
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("GET", 400)
        self.assertEqual(resp.data, b'Error!')
        resp = self.res.get_response_to("PUT", 400)
        self.assertEqual(resp.data, b'Error!')

        self.res.reset()
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("GET", 400)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("PUT", 400)
        self.assertEqual(resp.data, b'')
        
    def test_set_bytes_body(self):
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("GET", 400)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("PUT", 400)
        self.assertEqual(resp.data, b'')

        self.res.set_bytes_body_for(b'Ready!', "GET", 200)
        self.res.set_bytes_body_for(b'Error!')
        self.res.set_header("Content-Type", "application/octet-stream")
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.data, b'Ready!')
        resp = self.res.get_response_to("GET", 400)
        self.assertEqual(resp.data, b'Error!')
        resp = self.res.get_response_to("PUT", 400)
        self.assertEqual(resp.data, b'Error!')

        self.res.set_header_for("Content-Type", "application/json", "GET", 200)
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("GET", 400)
        self.assertEqual(resp.data, b'Error!')
        resp = self.res.get_response_to("PUT", 400)
        self.assertEqual(resp.data, b'Error!')

        self.res.reset()
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("GET", 400)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("PUT", 400)
        self.assertEqual(resp.data, b'')
        
    def test_set_json_body(self):
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("GET", 400)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("PUT", 400)
        self.assertEqual(resp.data, b'')

        self.res.set_json_body_for("Ready!", "GET", 200, ["application/json", "text/json"])
        self.res.set_json_body_for({"message": "Error!"})
        self.res.set_header("Content-Type", "application/json")
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.data, b'"Ready!"')
        resp = self.res.get_response_to("GET", 400)
        self.assertEqual(resp.data, b'{"message": "Error!"}')
        resp = self.res.get_response_to("PUT", 400)
        self.assertEqual(resp.data, b'{"message": "Error!"}')

        self.res.set_header_for("Content-Type", "text/plain", "GET", 200)
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("GET", 400)
        self.assertEqual(resp.data, b'{"message": "Error!"}')
        resp = self.res.get_response_to("PUT", 400)
        self.assertEqual(resp.data, b'{"message": "Error!"}')

        self.res.reset()
        resp = self.res.get_response_to("GET", 200)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("GET", 400)
        self.assertEqual(resp.data, b'')
        resp = self.res.get_response_to("PUT", 400)
        self.assertEqual(resp.data, b'')
        

if __name__ == '__main__':
    unittest.main()
