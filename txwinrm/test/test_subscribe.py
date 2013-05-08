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
from .tools import create_get_elem_func
from ..subscribe import _find_subscription_id, _find_enumeration_context, \
    _find_events, Event, System, RenderingInfo, EventSubscription

DATADIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data_subscribe")
get_elem = create_get_elem_func(DATADIR)


class FakeRequestSender(object):

    hostname = 'fake_host'

    def send_request(self, request_template_name, **kwargs):
        elem = None
        if request_template_name == 'subscribe':
            elem = get_elem('subscribe_resp.xml')
        elif request_template_name == 'event_pull':
            if kwargs['enumeration_context'] == \
                    'uuid:05071354-C4AD-4745-AA80-1127029F660E':
                elem = get_elem('pull_resp_02.xml')
            else:
                elem = get_elem('pull_resp_01.xml')
        return defer.succeed(elem)


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
        self.maxDiff = None
        elem = get_elem('pull_resp_01.xml')
        actual = list(_find_events(elem))
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


class TestEventSubscription(unittest.TestCase):

    def setUp(self):
        self._subscription = EventSubscription(FakeRequestSender())

    def tearDown(self):
        self._subscription = None

    @defer.inlineCallbacks
    def test_subscribe(self):
        yield self._subscription.subscribe()
        self.assertIsNotNone(self._subscription._subscription_id)
        self.assertIsNotNone(self._subscription._enumeration_context)

    @defer.inlineCallbacks
    def test_pull(self):
        yield self._subscription.subscribe()
        ec = self._subscription._enumeration_context
        events = []

        def append_event(event):
            events.append(event)

        yield self._subscription.pull(append_event)
        self.assertIsNotNone(self._subscription._subscription_id)
        self.assertIsNotNone(self._subscription._enumeration_context)
        self.assertNotEqual(ec, self._subscription._enumeration_context)
        self.assertTrue(events)
        self.assertEqual(1, len(events))

    def test_unsubscribe(self):
        self._subscription.subscribe()

        def do_nothing(event):
            pass

        self._subscription.pull(do_nothing)
        self._subscription.unsubscribe()
        self.assertIsNone(self._subscription._subscription_id)
        self.assertIsNone(self._subscription._enumeration_context)


if __name__ == '__main__':
    unittest.main()
