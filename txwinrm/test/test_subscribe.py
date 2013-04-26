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
from datetime import datetime
from xml.etree import cElementTree as ET
from ..subscribe import _find_subscription_id, _find_enumeration_context, \
    _find_events, Event, System, RenderingInfo, EventSubscription

DATADIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data_subscribe")


def get_elem(filename):
    with open(os.path.join(DATADIR, filename)) as f:
        return ET.fromstring(f.read())


class TestXmlParsing(unittest.TestCase):

    def test_find_subscription_id(self):
        elem = get_elem('subscribe_resp.xml')
        actual = _find_subscription_id(elem)
        expected = '885E9924-235C-44EB-9834-B3440B7DCD38'
        self.assertEqual(actual, expected)

    def test_find_enumeration_context(self):
        elem = get_elem('subscribe_resp.xml')
        actual = _find_enumeration_context(elem)
        expected = 'uuid:00A69F40-AF0D-4E6D-93BD-EFE6AADC3F51'
        self.assertEqual(actual, expected)

    def test_find_events(self):
        elem = get_elem('pull_resp.xml')
        actual = _find_events(elem)
        expected = [
            Event(
                system=System(
                    provider='EventCreate',
                    event_id=1,
                    event_id_qualifiers=0,
                    level=2,
                    task=0,
                    keywords=0x80000000000000,
                    time_created=datetime(2013, 4, 25, 21, 23, 39),
                    event_record_id=3847,
                    channel='Application',
                    computer='AMAZONA-Q2R281F',
                    user_id='S-1-5-21-4253355731-4135319224-1610184190-500'),
                data='test_from_gilroy_cmd_003',
                rendering_info=RenderingInfo(
                    culture='en-US',
                    message='test_from_gilroy_cmd_003',
                    level='Error',
                    opcode='Info',
                    keywords=['Classic']))]
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(actual, expected)


class _FakeSubscriber(object):

    def subscribe(self, event_query):
        return get_elem('subscribe_resp.xml')

    def pull(self):
        return get_elem('pull_resp.xml')

    def unsubscribe(self):
        return


class TestEventSubscription(unittest.TestCase):

    def setUp(self):
        self._subscription = EventSubscription(_FakeSubscriber())

    def tearDown(self):
        self._subscription = None

    def test_subscribe(self):
        self._subscription.subscribe()
        self.assertIsNotNone(self._subscription._subscription_id)
        self.assertIsNotNone(self._subscription._enumeration_context)

    def test_pull(self):
        self._subscription.subscribe()
        ec = self._subscription._enumeration_context
        events = self._subscription.pull()
        self.assertIsNotNone(self._subscription._subscription_id)
        self.assertIsNotNone(self._subscription._enumeration_context)
        self.assertNotEqual(ec, self._subscription._enumeration_context)
        self.assertTrue(events)
        self.assertEqual(1, len(events))

    def test_unsubscribe(self):
        self._subscription.subscribe()
        self._subscription.pull()
        self._subscription.unsubscribe()
        self.assertIsNone(self._subscription._subscription_id)
        self.assertIsNone(self._subscription._enumeration_context)


if __name__ == '__main__':
    unittest.main()
