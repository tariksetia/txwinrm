##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

from twisted.trial import unittest
from .. import winrs


class TestApp(unittest.TestCase):

    def test_winrs(self):
        winrs

if __name__ == '__main__':
    unittest.main()
