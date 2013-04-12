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
from xml.etree import cElementTree
from pprint import pformat
from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol
from twisted.internet.error import TimeoutError
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from .response import SaxResponseHandler
from . import constants as c

log = logging.getLogger('zen.winrm')


# general-purpose code, used by enumerate and shell/cmd -----------------------

_XML_WHITESPACE_PATTERN = re.compile(r'>\s+<')
_MARKER = object()
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
    tree = cElementTree.fromstring(xml_str)
    text = tree.findtext('.//{' + c.XML_NS_SOAP_1_2 + '}Text').strip()
    detail = tree.findtext('.//{' + c.XML_NS_SOAP_1_2 + '}Detail/*/*').strip()
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


def get_request_template(name):
    if _REQUEST_TEMPLATES is None:
        basedir = os.path.dirname(os.path.abspath(__file__))
        for name in 'enumerate', 'pull', \
                    'create', 'command', 'receive', 'signal', 'delete':
            filename = '{0}.xml'.format(name)
            path = os.path.join(basedir, 'request', filename)
            with open(path) as f:
                _REQUEST_TEMPLATES[name] = \
                    _XML_WHITESPACE_PATTERN.sub('><', f.read()).strip()
    return _REQUEST_TEMPLATES


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


# enumerate-specific ----------------------------------------------------------

_MAX_REQUESTS_PER_ENUMERATION = 9999
_DEFAULT_RESOURCE_URI = '{0}/*'.format(c.WMICIMV2)


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

    def __init__(self, handler):
        self._handler = handler

    @defer.inlineCallbacks
    def enumerate(self, hostname, username, password, wql,
                  resource_uri=_DEFAULT_RESOURCE_URI):
        """
        Runs a remote WQL query.
        """
        url, headers = get_url_and_headers(hostname, username, password)
        request_template_name = 'enumerate'
        enumeration_context = None
        accumulator = ItemsAccumulator()
        try:
            for i in xrange(_MAX_REQUESTS_PER_ENUMERATION):
                response = yield send_request(
                    url, headers, request_template_name,
                    resource_uri=resource_uri, wql=wql,
                    enumeration_context=enumeration_context)
                log.debug("{0} HTTP status: {1}".format(
                    hostname, response.code))
                enumeration_context = yield self._handler.handle_response(
                    response, accumulator)
                if not enumeration_context:
                    break
                request_template_name = 'pull'
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


def create_winrm_client():
    handler = SaxResponseHandler()
    return create_winrm_client_with_handler(handler)


def create_winrm_client_with_handler(handler):
    return WinrmClient(handler)


# shell/cmd-specific ----------------------------------------------------------

_MAX_REQUESTS_PER_COMMAND = 9999


class CommandResponse(object):

    def __init__(self, stdout, stderr, exit_code):
        self._stdout = stdout
        self._stderr = stderr
        self._exit_code = exit_code

    @property
    def stdout(self):
        return self._stdout

    @property
    def stderr(self):
        return self._stderr

    @property
    def exit_code(self):
        return self._exit_code


class _StringProtocol(Protocol):

    def __init__(self):
        self.d = defer.Deferred()
        self._data = []

    def dataReceived(self, data):
        self._data.append(data)

    def connectionLost(self, reason):
        self.d.callback(''.join(self._data))


class WinrsClient(object):

    @defer.inlineCallbacks
    def run_commands(self, hostname, username, password, commands):
        """
        Run commands in a remote shell like the winrs application on Windows.
        Accepts multiple commands. Returns a dictionary with the following
        structure:
            {<command>: CommandResponse
                             .stdout = [<stripped-line>, ...]
                             .stderr = [<stripped-line>, ...]
                             .exit_code = <int>
             ...}
        """
        url, headers = self._request_helper.get_url_and_headers(
            hostname, username, password)
        shell_id = yield self._create_shell(url, headers)
        cmd_responses = []
        for command in commands:
            cmd_response = yield self._run_command(
                hostname, url, headers, command, shell_id)
            cmd_responses.append(cmd_response)
        yield self._delete_shell(url, headers, shell_id)
        defer.returnValue(cmd_responses)

    @defer.inlineCallbacks
    def _create_shell(self, url, headers):
        resp = yield send_request(url, headers, 'create')
        proto = _StringProtocol()
        resp.deliverBody(proto)
        xml_str = yield proto.d
        tree = cElementTree.fromstring(xml_str)
        xpath = './/{' + c.XML_NS_WS_MAN + '}Selector[@Name="ShellId"]'
        shell_id = tree.findtext(xpath).strip()
        defer.returnValue(shell_id)

    @defer.inlineCallbacks
    def _run_command(self, url, headers, shell_id, command):
        command_resp = yield send_request(
            url, headers, 'command', shell_id=shell_id)
        proto = _StringProtocol()
        command_resp.deliverBody(proto)
        xml_str = yield proto.d
        tree = cElementTree.fromstring(xml_str)
        xpath = './/{' + c.XML_NS_MSRSP + '}CommandId'
        command_id = tree.findtext(xpath).strip()
        stdout_parts = []
        stderr_parts = []
        for i in xrange(_MAX_REQUESTS_PER_COMMAND):
            receive_resp = yield send_request(
                url, headers, 'receive', shell_id=shell_id,
                command_id=command_id)

            stdout_parts.append(stdout_part)
            stderr_parts.append(stderr_part)

            if exit_code is not None:
                break
        else:
            raise Exception("Reached max requests per command.")
        yield _send_request(
            url, headers, 'signal', shell_id=shell_id, command_id=command_id)
        stdout = ''.join(stdout_parts).splitlines()
        stderr = ''.join(stderr_parts).splitlines()
        defer.returnValue(CommandResponse(stdout, stderr, exit_code))

    @defer.inlineCallbacks
    def _delete_shell(self, url, headers, shell_id):
        yield send_request(url, headers, 'cmd_delete', shell_id=shell_id)


class WinrsClientFactory(object):



    def create_winrs_client(self):
        return WinrsClient(_agent(), self.request_templates)
