##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

import copy
import logging
from collections import namedtuple
from httplib import BAD_REQUEST, UNAUTHORIZED, FORBIDDEN, OK
import shlex
from cStringIO import StringIO

from twisted.internet import reactor
from twisted.internet.defer import (
    inlineCallbacks,
    returnValue,
    DeferredSemaphore,
    succeed
)
from twisted.internet.error import TimeoutError

try:
    from twisted.web.client import ResponseFailed
    ResponseFailed
except ImportError:
    class ResponseFailed(Exception):
        pass

from . import constants as c
from .util import (
    _authenticate_with_kerberos,
    _get_agent,
    verify_conn_info,
    _CONTENT_TYPE,
    _ENCRYPTED_CONTENT_TYPE,
    Headers,
    _get_basic_auth_header,
    _get_request_template,
    _StringProducer,
    get_auth_details,
    UnauthorizedError,
    ForbiddenError,
    RequestError,
    _ErrorReader,
    _StringProtocol,
    ET,
)
from .shell import (
    _find_shell_id,
    _build_command_line_elem,
    _find_command_id,
    _MAX_REQUESTS_PER_COMMAND,
    _find_stream,
    _find_exit_code,
    CommandResponse,
    _stripped_lines
)
from .enumerate import (
    DEFAULT_RESOURCE_URI,
    SaxResponseHandler,
    _MAX_REQUESTS_PER_ENUMERATION
)
from .SessionManager import SESSION_MANAGER, Session
kerberos = None
LOG = logging.getLogger('winrm')

EnumInfo = namedtuple('EnumInfo', ['wql', 'resource_uri'])


def _build_ps_command_line_elem(ps_command, ps_script):
    """Build PowerShell command line elements without splitting
    the actual ps script into arguments. using _build_command_line_elem
    with a ps script splits the script into separate arguments.  Remote
    Windows shell inserts spaces when reconstituting the script.

    ps_command - powershell command with arguments as string
        e.g. 'powershell -NoLogo -NonInteractive -NoProfile -Command'
    ps_script - script to be run in powershell as single line string
        e.g. "& {get-counter -counter \"\memory\pages output/sec\" }"
    """
    command_line_parts = shlex.split(ps_command, posix=False)
    # ensure '-command' is last
    if command_line_parts[-1:][0].lower() != '-command':
        index = 0
        for option in command_line_parts:
            if option.lower() == '-command':
                command_line_parts.pop(index)
                break
            index += 1
        command_line_parts.append(option)
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
    arguments_elem = ET.Element('{%s}Arguments' % c.XML_NS_MSRSP)
    arguments_elem.text = ps_script
    command_line_elem.append(arguments_elem)
    tree = ET.ElementTree(command_line_elem)
    str_io = StringIO()
    tree.write(str_io, encoding='utf-8')
    return str_io.getvalue()


class WinRMSession(Session):
    '''
    Session class to keep track of single winrm connection
    '''
    def __init__(self):
        super(WinRMSession, self).__init__()

        # twisted agent to send http/https requests
        self._agent = _get_agent()

        # our kerberos context for encryption/decryption
        self._gssclient = None

        # url for session
        self._url = None

        # headers to use for requests
        self._headers = None

        # connection info.  see util.ConnectionInfo
        self._conn_info = None

        # DeferredSemaphore so that we complete one transaction/conversation
        # at a time.  Windows cannot handle mixed transaction types on one
        # connection.
        self.sem = DeferredSemaphore(1)

        self._refresh_dc = None

    def is_kerberos(self):
        return self._conn_info.auth_type == 'kerberos'

    def decrypt_body(self, body):
        return self._gssclient.decrypt_body(body)

    def _set_headers(self):
        if self._headers:
            return self._headers
        if self._conn_info.auth_type == 'basic':
            self._headers = Headers(_CONTENT_TYPE)
            self._headers.addRawHeader('Connection', self._conn_info.connectiontype)
            self._headers.addRawHeader(
                'Authorization', _get_basic_auth_header(self._conn_info))
        elif self.is_kerberos():
            self._headers = Headers(_ENCRYPTED_CONTENT_TYPE)
            self._headers.addRawHeader('Connection', self._conn_info.connectiontype)
        return self._headers

    @inlineCallbacks
    def _deferred_login(self, client=None):
        if client:
            self._conn_info = client._conn_info
        self._url = "{c.scheme}://{c.ipaddress}:{c.port}/wsman".format(c=self._conn_info)
        if self.is_kerberos():
            self._gssclient = yield _authenticate_with_kerberos(self._conn_info, self._url, self._agent)
            returnValue(self._gssclient)
        else:
            returnValue('basic_auth_token')

    @inlineCallbacks
    def _deferred_logout(self):
        # close connections so we do not end up with orphans
        # return a Deferred()
        self.loggedout = True
        if self._agent and hasattr(self._agent, 'closeCachedConnections'):
            # twisted 11 has no return and is part of the Agent
            return succeed(self._agent.closeCachedConnections())
        elif self._agent:
            # twisted 12 returns a Deferred
            return self._agent._pool.closeCachedConnections()
        else:
            # no agent
            return succeed(None)

    @inlineCallbacks
    def handle_response(self, request, response, client):
        if response.code == UNAUTHORIZED or response.code == BAD_REQUEST:
            # check to see if we need to re-authorize due to lost connection or bad request error
            if self._gssclient is not None:
                self._gssclient.cleanup()
                self._gssclient = None
                self._token = None
                self._agent = _get_agent()
                self._login_d = None
                yield SESSION_MANAGER.init_connection(client, WinRMSession)
                try:
                    yield self._set_headers()
                    encrypted_request = self._gssclient.encrypt_body(request)
                    if not encrypted_request.startswith("--Encrypted Boundary"):
                        self._headers.setRawHeaders('Content-Type', _CONTENT_TYPE['Content-Type'])
                    body_producer = _StringProducer(encrypted_request)
                    response = yield self._agent.request(
                        'POST', self._url, self._headers, body_producer)
                except Exception as e:
                    raise e
            if response.code == UNAUTHORIZED:
                if self.is_kerberos():
                    if not kerberos:
                        from .util import kerberos
                    auth_header = response.headers.getRawHeaders('WWW-Authenticate')[0]
                    auth_details = get_auth_details(auth_header)
                    try:
                        if auth_details:
                            self._gssclient._step(auth_details)
                    except kerberos.GSSError as e:
                        msg = "HTTP Unauthorized received.  "
                        "Kerberos error code {0}: {1}.".format(e.args[1][1], e.args[1][0])
                        raise Exception(msg)
                raise UnauthorizedError(
                    "HTTP Unauthorized received: Check username and password")
        if response.code == FORBIDDEN:
            raise ForbiddenError(
                "Forbidden: Check WinRM port and version")
        elif response.code != OK:
            if self.is_kerberos():
                reader = _ErrorReader(self._gssclient)
            else:
                reader = _ErrorReader()
            response.deliverBody(reader)
            message = yield reader.d
            raise RequestError("HTTP status: {}. {}".format(
                response.code, message))
        returnValue(response)

    @inlineCallbacks
    def send_request(self, request_template_name, client, envelope_size=None, **kwargs):
        response = yield self._send_request(
            request_template_name, client, envelope_size=envelope_size, **kwargs)
        proto = _StringProtocol()
        response.deliverBody(proto)
        body = yield proto.d
        if self.is_kerberos():
            xml_str = self._gssclient.decrypt_body(body)
        else:
            xml_str = yield body
        if LOG.isEnabledFor(logging.DEBUG):
            try:
                import xml.dom.minidom
                xml = xml.dom.minidom.parseString(xml_str)
                LOG.debug(xml.toprettyxml())
            except Exception:
                LOG.debug('Could not prettify response XML: "{0}"'.format(xml_str))
        returnValue(ET.fromstring(xml_str))

    @inlineCallbacks
    def _send_request(self, request_template_name, client, envelope_size=None,
                      locale=None, code_page=None, **kwargs):
        kwargs['envelope_size'] = envelope_size or client._conn_info.envelope_size
        kwargs['locale'] = locale or client._conn_info.locale
        kwargs['code_page'] = code_page or client._conn_info.code_page
        if self._login_d and not self._login_d.called:
            # check for a reconnection attempt so we do not send any requests
            # to a dead connection
            yield self._login_d
        LOG.debug('sending request: {0} {1}'.format(
            request_template_name, kwargs))
        request = _get_request_template(request_template_name).format(**kwargs)
        self._headers = self._set_headers()
        if self.is_kerberos():
            encrypted_request = self._gssclient.encrypt_body(request)
            if not encrypted_request.startswith("--Encrypted Boundary"):
                self._headers.setRawHeaders('Content-Type', _CONTENT_TYPE['Content-Type'])
            body_producer = _StringProducer(encrypted_request)
        else:
            body_producer = _StringProducer(request)
        try:
            response = yield self._agent.request(
                'POST', self._url, self._headers, body_producer)
        except Exception as e:
            raise e
        LOG.debug('received response {0} {1}'.format(
            response.code, request_template_name))
        response = yield self.handle_response(request, response, client)
        returnValue(response)

    def close_connection(self, client):
        try:
            self._refresh_dc.cancel()
        except Exception:
            pass

        # Close the connection after 60 seconds.  This will give other clients
        # enough time to keep the connection alive and continue using the same session.
        self._refresh_dc = reactor.callLater(60, SESSION_MANAGER.close_connection, client)


class WinRMClient(object):
    """Base winrm client class

    Contains core functionality for various types of winrm based clients
    """
    def __init__(self, conn_info):
        verify_conn_info(conn_info)
        self.key = None
        self._conn_info = conn_info
        self.session_manager = SESSION_MANAGER
        self._session = None
        self.ps_script = None

    @inlineCallbacks
    def init_connection(self):
        """Initialize a connection through the session_manager"""
        if self._session:
            try:
                self._refresh_dc.cancel()
            except Exception:
                pass
        yield self.session_manager.init_connection(self, WinRMSession)
        self._session = self.session_manager.get_connection(self.key)
        returnValue(None)

    def is_kerberos(self):
        return self._conn_info.auth_type == 'kerberos'

    def decrypt_body(self, body):
        return self._session.decrypt_body(body)

    @inlineCallbacks
    def send_request(self, request, **kwargs):
        if not self._session:
            yield self.init_connection()

        if not self._session:
            raise Exception('Could not connect to device {}'.format(self.conn_info.hostname))
        response = yield self._session.send_request(request, self, **kwargs)
        returnValue(response)

    @inlineCallbacks
    def _create_shell(self):
        elem = yield self.send_request('create')
        returnValue(_find_shell_id(elem))

    @inlineCallbacks
    def _delete_shell(self, shell_id):
        yield self.send_request('delete', shell_id=shell_id)
        returnValue(None)

    @inlineCallbacks
    def _signal_terminate(self, shell_id, command_id):
        yield self.send_request('signal',
                                shell_id=shell_id,
                                command_id=command_id,
                                signal_code=c.SHELL_SIGNAL_TERMINATE)
        returnValue(None)

    @inlineCallbacks
    def _signal_ctrl_c(self, shell_id, command_id):
        yield self.send_request('signal',
                                shell_id=shell_id,
                                command_id=command_id,
                                signal_code=c.SHELL_SIGNAL_CTRL_C)
        returnValue(None)

    @inlineCallbacks
    def _send_command(self, shell_id, command_line):
        if self.ps_script is not None:
            command_line_elem = _build_ps_command_line_elem(command_line,
                                                            self.ps_script)
        else:
            command_line_elem = _build_command_line_elem(command_line)
        LOG.debug('WinRMClient._send_command: sending command request '
                  '(shell_id={0}, command_line_elem={1})'.format(
                      shell_id, command_line_elem))
        command_elem = yield self.send_request(
            'command', shell_id=shell_id, command_line_elem=command_line_elem,
            timeout=self._conn_info.timeout)
        returnValue(command_elem)

    @inlineCallbacks
    def _send_receive(self, shell_id, command_id):
        receive_elem = yield self.send_request(
            'receive', shell_id=shell_id, command_id=command_id)
        returnValue(receive_elem)

    @inlineCallbacks
    def close_connection(self):
        yield self._session.close_connection(self)
        returnValue(None)


class SingleCommandClient(WinRMClient):
    """Client to send a single command to a winrm device"""
    def __init__(self, conn_info):
        super(SingleCommandClient, self).__init__(conn_info)
        self.key = (self._conn_info.ipaddress, 'short')

    @inlineCallbacks
    def run_command(self, command_line, ps_script=None):
        """Run a single command in the session's semaphore.  Windows must finish
        a command conversation before a new command or enumeration can start

        If running a powershell script, send it in separately with ps_script in
        "& {<actual script here>}" format
        e.g. command_line='powershell -NoLogo -NonInteractive -NoProfile -Command',
        ps_script='"& {get-counter -counter \\\"\memory\pages output/sec\\\" }"'
        """
        cmd_response = None
        self.ps_script = ps_script
        yield self.init_connection()
        try:
            cmd_response = yield self._session.sem.run(self.run_single_command,
                                                       command_line)
        except Exception:
            yield self.close_connection()
            raise
        returnValue(cmd_response)

    @inlineCallbacks
    def run_single_command(self, command_line):
        """
        Run a single command line in a remote shell like the winrs application
        on Windows. Returns a dictionary with the following
        structure:
            CommandResponse
                .stdout = [<non-empty, stripped line>, ...]
                .stderr = [<non-empty, stripped line>, ...]
                .exit_code = <int>
        """
        shell_id = yield self._create_shell()
        cmd_response = None
        try:
            cmd_response = yield self._run_command(shell_id, command_line)
        except TimeoutError:
            yield self.close_connection()
        yield self._delete_shell(shell_id)
        yield self.close_connection()
        returnValue(cmd_response)

    @inlineCallbacks
    def _run_command(self, shell_id, command_line):
        command_elem = yield self._send_command(shell_id, command_line)
        command_id = _find_command_id(command_elem)
        stdout_parts = []
        stderr_parts = []
        for i in xrange(_MAX_REQUESTS_PER_COMMAND):
            receive_elem = yield self._send_receive(shell_id, command_id)
            stdout_parts.extend(
                _find_stream(receive_elem, command_id, 'stdout'))
            stderr_parts.extend(
                _find_stream(receive_elem, command_id, 'stderr'))
            exit_code = _find_exit_code(receive_elem, command_id)
            if exit_code is not None:
                break
        else:
            raise Exception("Reached max requests per command.")
        yield self._signal_terminate(shell_id, command_id)
        stdout = _stripped_lines(stdout_parts)
        stderr = _stripped_lines(stderr_parts)
        returnValue(CommandResponse(stdout, stderr, exit_code))


class LongCommandClient(WinRMClient):
    """Client to run a single long running command to a winrm device"""
    def __init__(self, conn_info):
        super(LongCommandClient, self).__init__(conn_info)
        self._shell_id = None
        self._command_id = None
        self._exit_code = None

    @inlineCallbacks
    def start(self, command_line, ps_script=''):
        """Start long running command

        If running a powershell script, send it in separately with ps_script in
        "& {<actual script here>}" format
        e.g. command_line='powershell -NoLogo -NonInteractive -NoProfile -Command',
        ps_script='"& {get-counter -counter \\\"\memory\pages output/sec\\\" }"'

        """
        LOG.debug("LongRunningCommand run_command: {0}".format(command_line))
        self.key = (self._conn_info.ipaddress, command_line + str(ps_script))
        self.ps_script = ps_script
        yield self.init_connection()
        self._shell_id = yield self._create_shell()
        try:
            command_elem = yield self._send_command(self._shell_id,
                                                    command_line)
        except TimeoutError:
            yield self.close_connection()
            raise
        self._command_id = _find_command_id(command_elem)
        returnValue(None)

    @inlineCallbacks
    def receive(self):
        try:
            receive_elem = yield self._send_receive(self._shell_id, self._command_id)
        except TimeoutError:
            yield self.close_connection()
            raise
        stdout_parts = _find_stream(receive_elem, self._command_id, 'stdout')
        stderr_parts = _find_stream(receive_elem, self._command_id, 'stderr')
        self._exit_code = _find_exit_code(receive_elem, self._command_id)
        stdout = _stripped_lines(stdout_parts)
        stderr = _stripped_lines(stderr_parts)
        returnValue((stdout, stderr))

    @inlineCallbacks
    def stop(self, close=False):
        yield self._signal_ctrl_c(self._shell_id, self._command_id)
        try:
            stdout, stderr = yield self.receive()
        except TimeoutError:
            pass
        yield self._signal_terminate(self._shell_id, self._command_id)
        yield self._delete_shell(self._shell_id)
        if close:
            yield self.close_connection()
        returnValue(CommandResponse(stdout, stderr, self._exit_code))


class EnumerateClient(WinRMClient):
    """Client to send a single wmi query(WQL) to a winrm device

    Sends enumerate requests to a host running the WinRM service and returns
    a list of items.
    """

    def __init__(self, conn_info):
        super(EnumerateClient, self).__init__(conn_info)
        self._handler = SaxResponseHandler(self)
        self._hostname = conn_info.ipaddress
        self.key = (conn_info.ipaddress, 'short')

    @inlineCallbacks
    def enumerate(self, wql, resource_uri=DEFAULT_RESOURCE_URI):
        """Runs a remote WQL query."""
        yield self.init_connection()
        request_template_name = 'enumerate'
        enumeration_context = None
        items = []
        try:
            for i in xrange(_MAX_REQUESTS_PER_ENUMERATION):
                LOG.info('{0} "{1}" {2}'.format(
                    self._hostname, wql, request_template_name))
                response = yield self._session._send_request(
                    request_template_name,
                    self,
                    resource_uri=resource_uri,
                    wql=wql,
                    enumeration_context=enumeration_context)
                LOG.info("{0} {1} HTTP status: {2}".format(
                    self._hostname, wql, response.code))
                enumeration_context, new_items = \
                    yield self._handler.handle_response(response)
                items.extend(new_items)
                if not enumeration_context:
                    break
                request_template_name = 'pull'
            else:
                raise Exception("Reached max requests per enumeration.")
        except (ResponseFailed, RequestError, Exception) as e:
            if isinstance(e, ResponseFailed):
                for reason in e.reasons:
                    LOG.error('{0} {1}'.format(self._hostname, reason.value))
            else:
                LOG.info('{0} {1}'.format(self._hostname, e))
            raise
        returnValue(items)

    @inlineCallbacks
    def do_collect(self, enum_infos):
        """Run enumerations in the session's semaphore.  Windows must finish
        an enumeration before a new command or enumeration can start
        """
        items = {}
        yield self.init_connection()
        self._session = self.session_manager.get_connection(self.key)
        for enum_info in enum_infos:
            try:
                items[enum_info] = yield self._session.sem.run(self.enumerate,
                                                               enum_info.wql,
                                                               enum_info.resource_uri)
            except (UnauthorizedError, ForbiddenError):
                # Fail the collection for general errors.
                raise
            except RequestError:
                # Store empty results for other query-specific errors.
                continue

        yield self.close_connection()
        returnValue(items)


class AssociatorClient(EnumerateClient):
    """WinRM Client that can return wmi classes that are associated with
        another wmi class through a single property.
        First a regular wmi query is run to select objects from a class.
            e.g. 'select * from Win32_NetworkAdapter'
        Next we will loop through the results and run the associator query
        using a specific property of the object as input to return
        a result class.
            e.g. for interface in interfaces:
                "ASSOCIATORS OF {Win32_NetworkAdapter.DeviceID=interface.DeviceID} WHERE ResultClass=Win32_PnPEntity'
    """

    @inlineCallbacks
    def associate(self,
                  seed_class,
                  associations,
                  where=None,
                  resource_uri=DEFAULT_RESOURCE_URI,
                  fields=['*']):
        """Method to retrieve associated wmi classes based upon a
        property from a given class

        seed_class - wmi class which will be initially queried
        associations - list of dicts containing parameters for
            the 'ASSOCIATORS of {A}' wql statement.  We dequeue the
            dicts and can search results from previous wql query to
            search for nested associations.
                search_class - initial class to associate with
                search_property - property on search_class to match
                return_class - class which will be returned
                where_type - keyword of association type:
                    AssocClass = AssocClassName
                    RequiredAssocQualifier = QualifierName
                    RequiredQualifier = QualifierName
                    ResultClass = ClassName
                    ResultRole = PropertyName
                    Role = PropertyName
        where - wql where clause to narrow scope of initial query
        resource_uri - uri of resource.  this will be the same for both
            input and result classes.  Limitation of WQL
        fields - fields to return from seed_class on initial query

        returns dict of seed_class and all return_class results
            mapped by search_property

        see https://msdn.microsoft.com/en-us/library/aa384793(v=vs.85).aspx
        """
        associations_copy = copy.deepcopy(associations)
        items = {}
        wql = 'Select {} from {}'.format(','.join(fields), seed_class)
        if where:
            wql += ' where {}'.format(where)
        enum_info = EnumInfo(wql, resource_uri)
        results = yield self.do_collect([enum_info])

        try:
            input_results = results[enum_info]
        except KeyError:
            raise Exception('No results for seed class {}.'.format(seed_class))

        items[seed_class] = input_results
        while associations_copy:
            association = associations_copy.pop(0)
            associate_results = []
            prop_results = {}
            for item in input_results:
                try:
                    prop = getattr(item, association['search_property'])
                except AttributeError:
                    continue
                else:
                    wql = "ASSOCIATORS of {{{}.{}='{}'}} WHERE {}={}".format(
                        association['search_class'],
                        association['search_property'],
                        prop,
                        association['where_type'],
                        association['return_class'])
                    enum_info = EnumInfo(wql, resource_uri)
                    result = yield self.do_collect([enum_info])
                    associate_results.extend(result[enum_info])
                    prop_results[prop] = result[enum_info]

            items[association['return_class']] = prop_results
            input_results = associate_results
        returnValue(items)
