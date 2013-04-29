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
from datetime import datetime
from xml.etree import cElementTree as ET
from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from . import constants as c

log = logging.getLogger('zen.winrm')
_XML_WHITESPACE_PATTERN = re.compile(r'>\s+<')
_AGENT = None
_MAX_PERSISTENT_PER_HOST = 2
_CACHED_CONNECTION_TIMEOUT = 240
_CONNECT_TIMEOUT = 5
_NANOSECONDS_PATTERN = re.compile(r'\.(\d{6})(\d{3})')
_REQUEST_TEMPLATE_NAMES = (
    'enumerate', 'pull',
    'create', 'command', 'send', 'receive', 'signal', 'delete',
    'subscribe', 'event_pull', 'unsubscribe')
_REQUEST_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'request')
_REQUEST_TEMPLATES = {}


def _get_agent():
    global _AGENT
    if _AGENT is None:
        try:
            # HTTPConnectionPool has been present since Twisted version 12.1
            from twisted.web.client import HTTPConnectionPool
            pool = HTTPConnectionPool(reactor, persistent=True)
            pool.maxPersistentPerHost = _MAX_PERSISTENT_PER_HOST
            pool.cachedConnectionTimeout = _CACHED_CONNECTION_TIMEOUT
            _AGENT = Agent(
                reactor, connectTimeout=_CONNECT_TIMEOUT, pool=pool)
        except ImportError:
            try:
                # connectTimeout first showed up in Twisted version 11.1
                _AGENT = Agent(reactor, connectTimeout=_CONNECT_TIMEOUT)
            except TypeError:
                _AGENT = Agent(reactor)
    return _AGENT


class _StringProducer(object):
    """
    The length attribute must be a non-negative integer or the constant
    twisted.web.iweb.UNKNOWN_LENGTH. If the length is known, it will be used to
    specify the value for the Content-Length header in the request. If the
    length is unknown the attribute should be set to UNKNOWN_LENGTH. Since more
    servers support Content-Length, if a length can be provided it should be.
    """

    def __init__(self, body):
        self._body = body
        self.length = len(body)

    def startProducing(self, consumer):
        """
        This method is used to associate a consumer with the producer. It
        should return a Deferred which fires when all data has been produced.
        """
        consumer.write(self._body)
        return defer.succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass


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


def _get_request_template(name):
    if name not in _REQUEST_TEMPLATE_NAMES:
        raise Exception('Invalid request template name: {0}'.format(name))
    if name not in _REQUEST_TEMPLATES:
        path = os.path.join(_REQUEST_TEMPLATE_DIR, '{0}.xml'.format(name))
        with open(path) as f:
            _REQUEST_TEMPLATES[name] = \
                _XML_WHITESPACE_PATTERN.sub('><', f.read()).strip()
    return _REQUEST_TEMPLATES[name]


def _get_url_and_headers(hostname, username, password):
    url = "http://{hostname}:5985/wsman".format(hostname=hostname)
    authstr = "{0}:{1}".format(username, password)
    auth = 'Basic {0}'.format(base64.encodestring(authstr).strip())
    headers = Headers({'Content-Type': ['application/soap+xml;charset=UTF-8'],
                       'Authorization': [auth]})
    return url, headers


class RequestSender(object):

    def __init__(self, hostname, useranme, password):
        self._hostname = hostname
        self._url, self._headers = _get_url_and_headers(
            hostname, useranme, password)

    @property
    def hostname(self):
        return self._hostname

    @defer.inlineCallbacks
    def send_request(self, request_template_name, **kwargs):
        log.debug('sending request: {0} {1}'.format(
            request_template_name, kwargs))
        request = _get_request_template(request_template_name).format(**kwargs)
        log.debug(request)
        body_producer = _StringProducer(request)
        response = yield _get_agent().request(
            'POST', self._url, self._headers, body_producer)
        if response.code == httplib.UNAUTHORIZED:
            raise UnauthorizedError(
                "unauthorized, check username and password.")
        elif response.code != httplib.OK:
            reader = _ErrorReader()
            response.deliverBody(reader)
            message = yield reader.d
            raise RequestError("HTTP status: {0}. {1}".format(
                response.code, message))
        defer.returnValue(response)


class _StringProtocol(Protocol):

    def __init__(self):
        self.d = defer.Deferred()
        self._data = []

    def dataReceived(self, data):
        self._data.append(data)

    def connectionLost(self, reason):
        self.d.callback(''.join(self._data))


class EtreeRequestSender(RequestSender):
    """A request sender that returns an etree element"""

    @defer.inlineCallbacks
    def send_request(self, request_template_name, **kwargs):
        resp = yield RequestSender.send_request(
            self, request_template_name, **kwargs)
        proto = _StringProtocol()
        resp.deliverBody(proto)
        xml_str = yield proto.d
        defer.returnValue(ET.fromstring(xml_str))


def get_datetime(text):
    """
    Parse the date from a WinRM response and return a datetime object.
    """
    if text.endswith('Z'):
        if '.' in text:
            format = "%Y-%m-%dT%H:%M:%S.%fZ"
            date_string = _NANOSECONDS_PATTERN.sub(r'.\g<1>', text)
        else:
            format = "%Y-%m-%dT%H:%M:%SZ"
            date_string = text
    else:
        format = '%m/%d/%Y %H:%M:%S.%f'
    return datetime.strptime(date_string, format)
