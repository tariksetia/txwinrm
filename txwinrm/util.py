##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import os
import re
import base64
import logging
import httplib
from xml.etree import cElementTree as ET
from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from . import constants as c

log = logging.getLogger('zen.winrm')
_XML_WHITESPACE_PATTERN = re.compile(r'>\s+<')
_AGENT = None


def _get_agent():
    global _AGENT
    if _AGENT is None:
        try:
            # HTTPConnectionPool has been present since Twisted version 12.1
            from twisted.web.client import HTTPConnectionPool
            pool = HTTPConnectionPool(reactor, persistent=True)
            pool.maxPersistentPerHost = c.MAX_PERSISTENT_PER_HOST
            pool.cachedConnectionTimeout = c.CACHED_CONNECTION_TIMEOUT
            _AGENT = Agent(
                reactor, connectTimeout=c.CONNECT_TIMEOUT, pool=pool)
        except ImportError:
            try:
                # connectTimeout first showed up in Twisted version 11.1
                _AGENT = Agent(reactor, connectTimeout=c.CONNECT_TIMEOUT)
            except TypeError:
                _AGENT = Agent(reactor)
    return _AGENT


class _StringProducer(object):

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)


def _parse_error_message(xml_str):
    elem = ET.fromstring(xml_str)
    text = elem.findtext('.//{' + c.XML_NS_SOAP_1_2 + '}Text').strip()
    detail = elem.findtext('.//{' + c.XML_NS_SOAP_1_2 + '}Detail/*/*').strip()
    return "{0} {1}".format(text, detail)


class _ErrorReader(Protocol):

    def __init__(self):
        self.d = defer.Deferred()
        self._data = []

    def dataReceived(self, data):
        self._data.append(data)

    def connectionLost(self, reason):
        message = _parse_error_message(''.join(self._data))
        self.d.callback(message)


class RequestError(Exception):
    pass


class UnauthorizedError(RequestError):
    pass

_REQUEST_TEMPLATES = None


def _build_request_templates():
    global _REQUEST_TEMPLATES
    _REQUEST_TEMPLATES = {}
    basedir = os.path.dirname(os.path.abspath(__file__))
    for name in 'enumerate', 'pull', \
                'create', 'command', 'receive', 'signal', 'delete':
        filename = '{0}.xml'.format(name)
        path = os.path.join(basedir, 'request', filename)
        with open(path) as f:
            _REQUEST_TEMPLATES[name] = \
                _XML_WHITESPACE_PATTERN.sub('><', f.read()).strip()


def get_request_template(name):
    if _REQUEST_TEMPLATES is None:
        _build_request_templates()
    return _REQUEST_TEMPLATES[name]


def get_url_and_headers(hostname, username, password):
    url = "http://{hostname}:5985/wsman".format(hostname=hostname)
    authstr = "{0}:{1}".format(username, password)
    auth = 'Basic {0}'.format(base64.encodestring(authstr).strip())
    headers = Headers({'Content-Type': ['application/soap+xml;charset=UTF-8'],
                       'Authorization': [auth]})
    return url, headers


@defer.inlineCallbacks
def send_request(url, headers, request_template_name, **kwargs):
    request = get_request_template(request_template_name).format(**kwargs)
    log.debug(request)
    body = _StringProducer(request)
    response = yield _get_agent().request('POST', url, headers, body)
    if response.code == httplib.UNAUTHORIZED:
        raise UnauthorizedError("unauthorized, check username and password.")
    elif response.code != httplib.OK:
        reader = _ErrorReader()
        response.deliverBody(reader)
        message = yield reader.d
        raise RequestError("HTTP status: {0}. {1}".format(
            response.code, message))
    defer.returnValue(response)
