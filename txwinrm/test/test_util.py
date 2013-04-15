##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
This testing requires real Windows machines that are setup manually.
"""

import os
import unittest
from ..util import _parse_error_message


class TestErrorReader(unittest.TestCase):

    def test_max_concurrent(self):
        dirpath = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(dirpath, 'data_error', 'max_concurrent.xml')
        with open(path) as f:
            actual = _parse_error_message(f.read())
        expected = 'The WS-Management service cannot process the request. ' \
            'The maximum number of concurrent operations for this user has ' \
            'been exceeded. Close existing operations for this user, or ' \
            'raise the quota for this user. The WS-Management service ' \
            'cannot process the request. This user is allowed a maximum ' \
            'number of 15 concurrent operations, which has been exceeded. ' \
            'Close existing operations for this user, or raise the quota ' \
            'for this user.'
        self.assertEqual(actual, expected)

if __name__ == '__main__':
    unittest.main()
    # suite = unittest.TestLoader().loadTestsFromTestCase(TestDataType)
    # unittest.TextTestRunner().run(suite)
