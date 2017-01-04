##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

import logging

from twisted.internet import defer
from WinRMClient import AssociatorClient
from .util import (
    ConnectionInfo,
)

log = logging.getLogger('winrm')
# for use with seed_class of Win32_NetworkAdapter
interface_map = [{'return_class': 'Win32_PnPEntity',
                  'search_class': 'win32_NetworkAdapter',
                  'search_property': 'DeviceID',
                  'where_type': 'ResultClass'
                  }]
# for use with seed_class of Win32_DiskDrive
disk_map = [{'return_class': 'Win32_DiskDriveToDiskPartition',
             'search_class': 'Win32_DiskDrive',
             'search_property': 'DeviceID',
             'where_type': 'AssocClass'},
            {'return_class': 'Win32_LogicalDiskToPartition',
             'search_class': 'Win32_DiskPartition',
             'search_property': 'DeviceID',
             'where_type': 'AssocClass'
             }]


class WinrmAssociatorClient(object):

    @defer.inlineCallbacks
    def do_associate(self, conn_info):
        """
        """
        client = AssociatorClient(conn_info)
        items = {}

        items = yield client.associate(
            'Win32_DiskDrive',
            disk_map
        )

        defer.returnValue(items)


# ----- An example of usage...

if __name__ == '__main__':
    from pprint import pprint
    import logging
    from twisted.internet import reactor
    logging.basicConfig()
    winrm = WinrmAssociatorClient()

    # Enter your params here before running
    params = {
        'hostname': "",  # name of host
        'authtype': "",  # kerberos or basic
        'user': "",  # username
        'password': "",  # password
        'kdc': "",  # kdc address
        'ipaddress': ""  # ip address
    }

    ''' Remove this line and line at the end to run test
    @defer.inlineCallbacks
    def do_example_collect():
        connectiontype = 'Keep-Alive'
        conn_info = ConnectionInfo(
            params['hostname'],
            params['authtype'],
            params['user'],
            params['password'],
            "http",
            5985,
            connectiontype,
            "",
            params['kdc'],
            ipaddress=params['ipaddress'])

        items = yield winrm.do_associate(conn_info)
        pprint(items)
        pprint(items.keys())
        reactor.stop()

    reactor.callWhenRunning(do_example_collect)
    reactor.run()

    Remove this line to execute above code'''
