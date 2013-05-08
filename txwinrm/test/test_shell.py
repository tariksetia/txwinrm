##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

import os
from datetime import datetime
from twisted.trial import unittest
from twisted.internet import defer
from xml.etree import cElementTree as ET
from .tools import create_get_elem_func
from ..shell import _build_command_line_elem, _stripped_lines, \
    _find_shell_id, _find_command_id, _find_stream, _find_exit_code, \
    CommandResponse, SingleShotCommand, LongRunningCommand, Typeperf

DATADIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data_shell")
get_elem = create_get_elem_func(DATADIR)
COMMAND_ID = '75233C4B-10BC-4796-A767-2D95F553DEEC'

EXPECTED_COMMAND_LINE_ELEM = \
    '<rsp:CommandLine ' \
    'xmlns:rsp="http://schemas.microsoft.com/wbem/wsman/1/windows/shell">' \
    '<rsp:Command>typeperf</rsp:Command>' \
    '<rsp:Arguments>"\Processor(_Total)\% Processor Time"</rsp:Arguments>' \
    '<rsp:Arguments>-sc</rsp:Arguments>' \
    '<rsp:Arguments>1</rsp:Arguments>' \
    '</rsp:CommandLine>'


class FakeRequestSender(object):

    hostname = 'fake_host'
    _receive_resp = 'receive_resp_01.xml'

    def send_request(self, request_template_name, **kwargs):
        elem = None

        if request_template_name == 'command':
            elem = get_elem('command_resp.xml')

        elif request_template_name == 'create':
            elem = get_elem('create_resp.xml')

        elif request_template_name == 'receive':
            elem = get_elem(self._receive_resp)
            self._receive_resp = 'receive_resp_02.xml'

        return defer.succeed(elem)


class TestBuildCommandLineElem(unittest.TestCase):

    def test_build_command_line_elem(self):
        actual = _build_command_line_elem(
            r'typeperf "\Processor(_Total)\% Processor Time" -sc 1')
        self.assertEqual(actual, EXPECTED_COMMAND_LINE_ELEM)


class TestStrippedLines(unittest.TestCase):

    def test_stripped_lines(self):
        source = ['foo\nbar', 'quux blah\n', '\nblam bloo', 'flim flam floo']
        actual = _stripped_lines(source)
        expected = ['foo', 'barquux blah', 'blam blooflim flam floo']
        self.assertEqual(actual, expected)


def get_elem(filename):
    with open(os.path.join(DATADIR, filename)) as f:
        return ET.fromstring(f.read())


class TestXmlParsing(unittest.TestCase):

    def test_find_shell_id(self):
        elem = get_elem('create_resp.xml')
        actual = _find_shell_id(elem)
        expected = '81DF6FC4-08CB-4FB4-A75B-33B422885199'
        self.assertEqual(actual, expected)

    def test_find_command_id(self):
        elem = get_elem('command_resp.xml')
        actual = _find_command_id(elem)
        expected = COMMAND_ID
        self.assertEqual(actual, expected)

    def test_find_stdout(self):
        elem = get_elem('receive_resp_01.xml')
        actual = list(_find_stream(elem, COMMAND_ID, 'stdout'))
        expected = [
            '\r\n',
            '"(PDH-CSV 4.0)"',
            ',"\\\\AMAZONA-Q2R281F\\Processor(_Total)\\% Processor Time"']
        self.assertEqual(actual, expected)

        elem = get_elem('receive_resp_02.xml')
        actual = list(_find_stream(elem, COMMAND_ID, 'stdout'))
        expected = [
            '\r\n"04/11/2013 17:55:02.335"',
            ',"0.024353"\r\nExiting, please wait...                         '
            '\r\nThe command completed successfully.\r\n\r\r',
            '']
        self.assertEqual(actual, expected)

    def test_find_stderr(self):
        elem = get_elem('receive_resp_01.xml')
        actual = list(_find_stream(elem, COMMAND_ID, 'stderr'))
        expected = []
        self.assertEqual(actual, expected)

        elem = get_elem('receive_resp_02.xml')
        actual = list(_find_stream(elem, COMMAND_ID, 'stderr'))
        expected = ['']
        self.assertEqual(actual, expected)

    def test_find_exit_code(self):
        elem = get_elem('receive_resp_01.xml')
        actual = _find_exit_code(elem, COMMAND_ID)
        self.assertIsNone(actual)

        elem = get_elem('receive_resp_02.xml')
        actual = _find_exit_code(elem, COMMAND_ID)
        expected = 0
        self.assertEqual(actual, expected)


class TestCommandResponse(unittest.TestCase):

    def test_command_response(self):
        stdout = 'foo'
        stderr = 'bar'
        exit_code = 'quux'
        resp = CommandResponse(stdout, stderr, exit_code)
        self.assertEqual(resp.stdout, stdout)
        self.assertEqual(resp.stderr, stderr)
        self.assertEqual(resp.exit_code, exit_code)
        self.assertEqual(
            repr(resp),
            "{'exit_code': 'quux', 'stderr': 'bar', 'stdout': 'foo'}")


class TestSingleShotCommand(unittest.TestCase):

    @defer.inlineCallbacks
    def test_run_command(self):
        command = SingleShotCommand(FakeRequestSender())
        cmd_response = yield command.run_command('foo')
        self.assertEqual(cmd_response.exit_code, 0)
        self.assertEqual(cmd_response.stderr, [])
        expected_stdout = ['"(PDH-CSV 4.0)","\\\\AMAZONA-Q2R281F\\Processor(_T'
                           'otal)\\% Processor Time"',
                           '"04/11/2013 17:55:02.335","0.024353"',
                           'Exiting, please wait...',
                           'The command completed successfully.']
        self.assertEqual(cmd_response.stdout, expected_stdout)


class TestLongRunningCommand(unittest.TestCase):

    def setUp(self):
        self._command = LongRunningCommand(FakeRequestSender())

    def tearDown(self):
        self._command = None

    @defer.inlineCallbacks
    def test_start(self):
        yield self._command.start('foo')
        self.assertEqual(self._command._shell_id,
                         '81DF6FC4-08CB-4FB4-A75B-33B422885199')
        self.assertEqual(self._command._command_id,
                         '75233C4B-10BC-4796-A767-2D95F553DEEC')
        self.assertIsNone(self._command._exit_code)

    @defer.inlineCallbacks
    def test_receive(self):
        yield self._command.start('foo')
        stdout, stderr = yield self._command.receive()
        self.assertEqual(stdout, ['"(PDH-CSV 4.0)","\\\\AMAZONA-Q2R281F\\Proce'
                                  'ssor(_Total)\\% Processor Time"'])
        self.assertEqual(stderr, [])
        self.assertIsNone(self._command._exit_code)

    @defer.inlineCallbacks
    def test_stop(self):
        yield self._command.start('foo')
        yield self._command.receive()
        cmd_response = yield self._command.stop()
        self.assertEqual(cmd_response.exit_code, 0)
        self.assertEqual(cmd_response.stderr, [])
        expected_stdout = ['"04/11/2013 17:55:02.335","0.024353"',
                           'Exiting, please wait...',
                           'The command completed successfully.']
        self.assertEqual(cmd_response.stdout, expected_stdout)


class TestTypeperf(unittest.TestCase):

    def setUp(self):
        self._command = Typeperf(LongRunningCommand(FakeRequestSender()))

    def tearDown(self):
        self._command = None

    @defer.inlineCallbacks
    def test_start(self):
        self.assertEqual(self._command._counters, None)
        self.assertEqual(self._command._row_count, 0)
        yield self._command.start(['foo'])
        self.assertEqual(self._command._counters, ['foo'])
        self.assertEqual(self._command._row_count, 0)

    @defer.inlineCallbacks
    def test_receive(self):
        yield self._command.start(['foo'])
        dct, stderr = yield self._command.receive()
        self.assertEqual(dct, dict(foo=[]))
        self.assertEqual(stderr, [])
        self.assertEqual(self._command._counters, ['foo'])
        self.assertEqual(self._command._row_count, 1)
        dct, stderr = yield self._command.receive()
        self.assertEqual(dct, dict(foo=[(
            datetime(2013, 4, 11, 17, 55, 2, 335000), 0.024353)]))
        self.assertEqual(stderr, [])
        self.assertEqual(self._command._counters, ['foo'])
        self.assertEqual(self._command._row_count, 4)

    @defer.inlineCallbacks
    def test_stop(self):
        yield self._command.start(['foo'])
        yield self._command.receive()
        yield self._command.stop()
        self.assertEqual(self._command._counters, None)
        self.assertEqual(self._command._row_count, 0)

if __name__ == '__main__':
    unittest.main()
