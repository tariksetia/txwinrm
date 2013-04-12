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
from pprint import pformat
from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol
from twisted.internet.error import TimeoutError
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from .response import SaxResponseHandler
from . import constants as c

log = logging.getLogger('zen.winrm')
MAX_REQUESTS_PER_ENUMERATION = 9999
XML_WHITESPACE_PATTERN = re.compile(r'>\s+<')
_MARKER = object()


def get_request_template(name):
    basedir = os.path.dirname(os.path.abspath(__file__))
    request_fmt_filename = os.path.join(basedir, 'request', name + '.xml')
    with open(request_fmt_filename) as f:
        raw_request_template = f.read()
    return XML_WHITESPACE_PATTERN.sub('><', raw_request_template).strip()


class AddPropertyWithoutItemError(Exception):

    def __init__(self, msg):
        Exception("It is an illegal state for add_property to be called "
                  "before the first call to new_item. {0}".format(msg))


class Item(object):

    def __repr__(self):
        return '\n' + pformat(vars(self), indent=4)


class ItemsAccumulator(object):
    """
    new_item() is called each time a new item is recognized in the
    enumerate and pull responses. add_property(name, value) is called with
    each property. All properties added between calls to new_item
    belong to a single item. It is an illegal state for add_property to
    be called before the first call to new_item. add_property being called
    multiple times with the same name within the same item indicates that
    the property is an array.
    """

    def __init__(self):
        self.items = []

    def new_item(self):
        self.items.append(Item())

    def add_property(self, name, value):
        if not self.items:
            raise AddPropertyWithoutItemError(
                "{0} = {1}".format(name, value))
        item = self.items[-1]
        prop = getattr(item, name, _MARKER)
        if prop is _MARKER:
            setattr(item, name, value)
            return
        if isinstance(prop, list):
            prop.append(value)
            return
        setattr(item, name, [prop, value])


class WinrmClient(object):

    def __init__(self, agent, handler, request_templates):
        self._agent = agent
        self._handler = handler
        self._request_templates = request_templates
        self._unauthorized_hosts = []
        self._timedout_hosts = []

    def _get_url_and_headers(self, hostname, username, password):
        if hostname in self._unauthorized_hosts:
            if log.isEnabledFor(logging.DEBUG):
                log.debug(hostname + " previously returned "
                                     "unauthorized. Skipping.")
            return
        if hostname in self._timedout_hosts:
            if log.isEnabledFor(logging.DEBUG):
                log.debug(hostname + " previously timed out. "
                                     "Skipping.")
            return
        url = "http://{hostname}:5985/wsman".format(hostname=hostname)
        authstr = "{username}:{password}".format(username=username,
                                                 password=password)
        auth = 'Basic ' + base64.encodestring(authstr).strip()
        headers = Headers(
            {'Content-Type': ['application/soap+xml;charset=UTF-8'],
             'Authorization': [auth]})
        return url, headers

    @defer.inlineCallbacks
    def enumerate(self, hostname, username, password, wql):
        """
        Runs a remote WQL query.
        """
        url, headers = self._get_url_and_headers(hostname, username, password)
        request_type = 'enumerate'
        resource_uri_prefix = c.WMICIMV2
        enumeration_context = None
        accumulator = ItemsAccumulator()
        try:
            for i in xrange(MAX_REQUESTS_PER_ENUMERATION):
                request_fmt = self._request_templates[request_type]
                request = request_fmt.format(
                    resource_uri=resource_uri_prefix + '/*',
                    wql=wql,
                    enumeration_context=enumeration_context)
                if log.isEnabledFor(logging.DEBUG):
                    log.debug(request)
                body = StringProducer(request)
                response = yield self._agent.request('POST', url, headers,
                                                     body)
                if log.isEnabledFor(logging.DEBUG):
                    log.debug("{0} HTTP status: {1}".format(
                        hostname, response.code))
                if response.code == httplib.UNAUTHORIZED:
                    if hostname in self._unauthorized_hosts:
                        return
                    self._unauthorized_hosts.append(hostname)
                    raise Unauthorized("unauthorized, check username and "
                                       "password.")
                if response.code != 200:
                    reader = ErrorReader(hostname, wql)
                    response.deliverBody(reader)
                    yield reader.d
                    raise Exception("HTTP status: {0}".format(response.code))
                enumeration_context = yield self._handler.handle_response(
                    response, accumulator)
                if not enumeration_context:
                    break
                request_type = 'pull'
            else:
                raise Exception("Reached max requests per enumeration.")
            defer.returnValue(accumulator.items)
        except TimeoutError, e:
            if hostname in self._timedout_hosts:
                return
            self._timedout_hosts.append(hostname)
            log.error('{0} {1}'.format(hostname, e))
            raise
        except Exception, e:
            log.error('{0} {1}'.format(hostname, e))
            raise

    @defer.inlineCallbacks
    def run_commands(self, hostname, username, password, commands):
        """
        Run commands in a remote shell like the winrs application on Windows.
        Accepts multiple commands. Returns a dictionary with the following
        structure:
            {<command>: dict(stdout=[<stripped-line>, ...],
                             stdin=[<stripped-line>, ...],
                             exit_code=<int>),
             ...}
        """
        url, headers = self._get_url_and_headers(hostname, username, password)


class WinrmClientFactory(object):

    agent = None
    request_templates = dict(enumerate=get_request_template('enumerate'),
                             pull=get_request_template('pull'))

    @classmethod
    def _get_or_create_agent(cls):
        if cls.agent is not None:
            return cls.agent
        try:
            # HTTPConnectionPool has been present since Twisted version 12.1
            from twisted.web.client import HTTPConnectionPool
            pool = HTTPConnectionPool(reactor, persistent=True)
            pool.maxPersistentPerHost = c.MAX_PERSISTENT_PER_HOST
            pool.cachedConnectionTimeout = c.CACHED_CONNECTION_TIMEOUT
            return Agent(reactor, connectTimeout=c.CONNECT_TIMEOUT, pool=pool)
        except ImportError:
            try:
                # connectTimeout first showed up in Twisted version 11.1
                return Agent(reactor, connectTimeout=c.CONNECT_TIMEOUT)
            except TypeError:
                return Agent(reactor)

    def create_winrm_client(self):
        handler = SaxResponseHandler()
        return self.create_winrm_client_with_handler(handler)

    def create_winrm_client_with_handler(self, handler):
        agent = self._get_or_create_agent()
        return WinrmClient(agent, handler, self.request_templates)


class ErrorReader(Protocol):

    def __init__(self, hostname, wql):
        self.d = defer.Deferred()
        self._hostname = hostname
        self._wql = wql
        self._data = ""

    def dataReceived(self, data):
        self._data += data

    def connectionLost(self, reason):
        from xml.etree import ElementTree
        tree = ElementTree.fromstring(self._data)
        log.error("{0._hostname} --> {0._wql}".format(self))
        ns = c.XML_NS_SOAP_1_2
        log.error(tree.findtext('.//{' + ns + '}Text').strip())
        log.error(tree.findtext('.//{' + ns + '}Detail/*/*').strip())
        self.d.callback(None)


class StringProducer(object):

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)


class Unauthorized(Exception):
    pass
