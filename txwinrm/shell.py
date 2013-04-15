##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
import shlex
import base64
from pprint import pformat
from cStringIO import StringIO
from twisted.internet import defer
from twisted.internet.protocol import Protocol
from xml.etree import cElementTree as ET
from . import constants as c
from .util import get_url_and_headers, send_request

log = logging.getLogger('zen.winrm')
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

    def __repr__(self):
        return pformat(dict(
            stdout=self.stdout, stderr=self.stderr, exit_code=self.exit_code))


class _StringProtocol(Protocol):

    def __init__(self):
        self.d = defer.Deferred()
        self._data = []

    def dataReceived(self, data):
        self._data.append(data)

    def connectionLost(self, reason):
        self.d.callback(''.join(self._data))


def _build_command_line_elem(command_line):
    command_line_parts = shlex.split(command_line, posix=False)
    prefix = "rsp"
    ET.register_namespace(prefix, c.XML_NS_MSRSP)
    command_line_elem = ET.Element('{%s}CommandLine' % c.XML_NS_MSRSP)
    command_elem = ET.Element('{%s}Command' % c.XML_NS_MSRSP)
    command_elem.text = command_line_parts[0]
    command_line_elem.append(command_elem)
    for arguments_text in command_line_parts[1:]:
        arguments_elem = ET.Element('{%s}Arguments' % c.XML_NS_MSRSP)
        arguments_elem.text = arguments_text
        command_line_elem.append(arguments_elem)
    tree = ET.ElementTree(command_line_elem)
    str_io = StringIO()
    tree.write(str_io)
    return str_io.getvalue()


def _stripped_lines(stream_parts):
    results = []
    for line in ''.join(stream_parts).splitlines():
        if line.strip():
            results.append(line.strip())
    return results


def _find_shell_id(elem):
    xpath = './/{%s}Selector[@Name="ShellId"]' % c.XML_NS_WS_MAN
    return elem.findtext(xpath).strip()


def _find_command_id(elem):
    xpath = './/{%s}CommandId' % c.XML_NS_MSRSP
    return elem.findtext(xpath).strip()


def _find_stream(elem, command_id, stream_name):
    xpath = './/{%s}Stream[@Name="%s"][@CommandId="%s"]' \
        % (c.XML_NS_MSRSP, stream_name, command_id)
    for elem in elem.findall(xpath):
        if elem.text is not None:
            yield base64.decodestring(elem.text)


def _find_exit_code(elem, command_id):
    command_state_xpath = './/{%s}CommandState[@CommandId="%s"]' \
        % (c.XML_NS_MSRSP, command_id)
    command_state_elem = elem.find(command_state_xpath)
    if command_state_elem is not None:
        exit_code_xpath = './/{%s}ExitCode' % c.XML_NS_MSRSP
        exit_code_text = command_state_elem.findtext(exit_code_xpath)
        return None if exit_code_text is None else int(exit_code_text)


class WinrsClient(object):

    def __init__(self, hostname, username, password):
        self._hostname = hostname
        self._username = username
        self._password = password
        self._url, self._headers = get_url_and_headers(
            hostname, username, password)

    @defer.inlineCallbacks
    def run_command(self, command):
        """
        Run commands in a remote shell like the winrs application on Windows.
        Accepts multiple commands. Returns a dictionary with the following
        structure:
            CommandResponse
                .stdout = [<non-empty, stripped line>, ...]
                .stderr = [<non-empty, stripped line>, ...]
                .exit_code = <int>
        """
        shell_id = yield self._create_shell()
        cmd_response = yield self._run_command(shell_id, command)
        yield self._delete_shell(shell_id)
        defer.returnValue(cmd_response)

    @defer.inlineCallbacks
    def _send_request(self, request_template_name, **kwargs):
        log.debug('sending winrs request: {0} {1}'.format(
            request_template_name, kwargs))
        resp = yield send_request(
            self._url, self._headers, request_template_name, **kwargs)
        proto = _StringProtocol()
        resp.deliverBody(proto)
        xml_str = yield proto.d
        defer.returnValue(ET.fromstring(xml_str))

    @defer.inlineCallbacks
    def _create_shell(self):
        elem = yield self._send_request('create')
        defer.returnValue(_find_shell_id(elem))

    @defer.inlineCallbacks
    def _run_command(self, shell_id, command_line):
        command_line_elem = _build_command_line_elem(command_line)
        command_elem = yield self._send_request(
            'command', shell_id=shell_id, command_line_elem=command_line_elem)
        command_id = _find_command_id(command_elem)
        stdout_parts = []
        stderr_parts = []
        for i in xrange(_MAX_REQUESTS_PER_COMMAND):
            receive_elem = yield self._send_request(
                'receive', shell_id=shell_id, command_id=command_id)
            stdout_parts.extend(
                _find_stream(receive_elem, command_id, 'stdout'))
            stderr_parts.extend(
                _find_stream(receive_elem, command_id, 'stderr'))
            exit_code = _find_exit_code(receive_elem, command_id)
            if exit_code is not None:
                break
        else:
            raise Exception("Reached max requests per command.")
        yield send_request(self._url, self._headers, 'signal',
                           shell_id=shell_id, command_id=command_id)
        stdout = _stripped_lines(stdout_parts)
        stderr = _stripped_lines(stderr_parts)
        defer.returnValue(CommandResponse(stdout, stderr, exit_code))

    @defer.inlineCallbacks
    def _delete_shell(self, shell_id):
        yield send_request(self._url, self._headers, 'delete',
                           shell_id=shell_id)
