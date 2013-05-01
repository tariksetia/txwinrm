##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import os
import unittest
import base64
from xml.etree import cElementTree as ET
from ..shell import _build_command_line_elem, _stripped_lines, \
    _find_shell_id, _find_command_id, _find_stream, _find_exit_code, \
    CommandResponse, SingleShotCommand

DATADIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data_shell")

COMMAND_ID = '75233C4B-10BC-4796-A767-2D95F553DEEC'

EXPECTED_COMMAND_LINE_ELEM = \
    '<rsp:CommandLine ' \
    'xmlns:rsp="http://schemas.microsoft.com/wbem/wsman/1/windows/shell">' \
    '<rsp:Command>typeperf</rsp:Command>' \
    '<rsp:Arguments>"\Processor(_Total)\% Processor Time"</rsp:Arguments>' \
    '<rsp:Arguments>-sc</rsp:Arguments>' \
    '<rsp:Arguments>1</rsp:Arguments>' \
    '</rsp:CommandLine>'


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

if __name__ == '__main__':
    unittest.main()
