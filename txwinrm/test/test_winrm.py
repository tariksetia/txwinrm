##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

from twisted.trial import unittest
from twisted.internet import defer
from .. import winrm


class Item(object):

    def __init__(self, left, right):
        self.left = left
        self.right = right


class Client(object):

    def enumerate(self, wql):
        return defer.succeed("foo")


class TestApp(unittest.TestCase):

    def test_get_vmpeak(self):
        actual = winrm.get_vmpeak()
        self.assertIsNotNone(actual)

    def test_print_items(self):
        winrm.print_items(
            [Item(1, 2), Item('foo', 'bar')], 'myhost', 'my wql query', True)

    @defer.inlineCallbacks
    def test_get_remote_process_stats(self):
        actual = yield winrm.get_remote_process_stats(Client())
        self.assertEqual(actual, 'foo')

if __name__ == '__main__':
    unittest.main()
