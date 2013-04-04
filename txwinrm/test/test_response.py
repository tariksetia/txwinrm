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

import unittest


class TestWinrm(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_select_star_vs_explicit_fields(self):
        """
        WQL queries that start with 'select *' have different tags in the XML
        response than queries which specify fields. 'select *' responses use
        the CIM class as the instance element's tag and as the namespace for
        the tags of each field. WQL queries that specify fields use XmlFragment
        as the instance element's tag and do not use a namespace for the tags
        of each field.The client should normalize both response types so the
        result is guaranteed to be consistent before further operations are
        performed on it. This test goes through a list of queries that
        explicitly list all fields for the CIM class. It runs the queries on
        each know host along with a 'select *' query and verifies that the
        results match.
        """
        

        for hostname, username, password in context.hosts:
            self._client.enumerate(hostname, username, password):

if __name__ == '__main__':
    unittest.main()
