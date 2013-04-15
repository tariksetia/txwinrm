##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import unittest
from ..shell import build_command_line_elem

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
        actual = build_command_line_elem(
            r'typeperf "\Processor(_Total)\% Processor Time" -sc 1')
        self.assertEqual(actual, EXPECTED_COMMAND_LINE_ELEM)

if __name__ == '__main__':
    unittest.main()
