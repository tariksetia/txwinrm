##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

"""
This testing requires real Windows machines that are setup manually.
"""

import os
from datetime import datetime
import unittest
from ..util import _parse_error_message, _get_agent, _StringProducer, \
    _get_request_template, get_datetime


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


class TestAgent(unittest.TestCase):

    def test_get_agent(self):
        agent = _get_agent()
        self.assertIsNotNone(agent)


class TestStringProducer(unittest.TestCase):

    def test_constructor(self):
        producer = _StringProducer('foo')
        self.assertEqual(producer._body, 'foo')
        self.assertEqual(producer.length, len('foo'))
        self.assertIsNone(producer.pauseProducing())
        self.assertIsNone(producer.stopProducing())


class TestRequestTemplate(unittest.TestCase):

    def test_get_request_template(self):
        templ = _get_request_template('enumerate')
        self.assertIn(
            'http://schemas.xmlsoap.org/ws/2004/09/enumeration/Enumerate',
            templ)


class TestGetDateTime(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_datetime(self):
        data = [("2013-04-09T15:42:20.4124Z",
                 datetime(2013, 4, 9, 15, 42, 20, 412400)),
                ("2013-04-09T15:42:20Z",
                 datetime(2013, 4, 9, 15, 42, 20)),
                ]
        for date_str, expected in data:
            actual = get_datetime(date_str)
            self.assertEqual(actual, expected)

    def test_2003_OperatingSystem(self):
        """
        Saw these date strings on test-win2003-1d Win32_OperatingSystem
        """
        data = [("2009-10-21T14:48:42-04:00",
                 datetime(2009, 10, 21, 14, 48, 42)),
                ("2013-05-24T15:06:05.359375-04:00",
                 datetime(2013, 5, 24, 15, 6, 5, 359375)),
                ("2013-06-07T14:27:22.874-04:00",
                 datetime(2013, 6, 7, 14, 27, 22, 874000)),
                ]
        for date_str, expected in data:
            actual = get_datetime(date_str)
            self.assertEqual(actual, expected)

if __name__ == '__main__':
    unittest.main()
    # suite = unittest.TestLoader().loadTestsFromTestCase(TestDataType)
    # unittest.TextTestRunner().run(suite)
