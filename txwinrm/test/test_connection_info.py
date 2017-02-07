#!/usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

import unittest

from ..util import *


class TestConnectionInfo(unittest.TestCase):
    def test_connection_info(self):
        conn_info = ConnectionInfo(
            hostname='hostname',
            auth_type='basic',
            username='username',
            password='password',
            scheme='http',
            port=5985,
            connectiontype='Keep-Alive',
            keytab='/test',
            dcip='10.10.10.10',
            trusted_realm='trusted_realm',
            trusted_kdc='10.10.20.20',
            ipaddress='10.10.10.2',
            service='wsman',
            envelope_size=512000,
            locale='en-US',
            code_page=65001,
            include_dir='/tmp')
        self.assertIsNone(verify_conn_info(conn_info))
        conn_info = ConnectionInfo(
            hostname='hostname',
            auth_type='basic',
            username='username',
            password='password',
            scheme='http',
            port=5985,
            connectiontype='Keep-Alive',
            keytab='/test',
            dcip='10.10.10.10',
            trusted_realm='trusted_realm',
            trusted_kdc='10.10.20.20',
            ipaddress='10.10.10.2',
            service='wsman',
            envelope_size=512000,
            locale='en-US',
            code_page=65001)
        self.assertIsNone(verify_conn_info(conn_info))
        conn_info = ConnectionInfo(
            hostname='hostname',
            auth_type='basic',
            username='username',
            password='password',
            scheme='http',
            port=5985,
            connectiontype='Keep-Alive',
            keytab='/test',
            dcip='10.10.10.10',
            trusted_realm='trusted_realm',
            trusted_kdc='10.10.20.20',
            ipaddress='10.10.10.2',
            service='wsman',
            envelope_size=512000,
            locale='en-US',
            code_page=65001,
            include_dir='/nonexistent')
        with self.assertRaises(Exception):
            verify_include_dir(conn_info)


if __name__ == '__main__':
    unittest.main()
    suite = unittest.TestLoader().loadTestsFromTestCase(TestConnectionInfo)
    unittest.TextTestRunner().run(suite)
