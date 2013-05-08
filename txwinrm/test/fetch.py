##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

"""
Fetch data for tests. Fetches target operating system version and uses that for
the name of a subfolder in test/data. Next, it fetches XML response for
'select *' queries, and saves to files under test/data/<os-version> with
filename <cim-class>_star.xml. Then it forms queries with all the properties
of the CIM class explicitly listed. It saves theses as <cim-class>_all.xml.
Later a unit test can test that the parser output matches for each star and all
XML file pair. <cim_class>.properties is also generated and is a list of all
properties.
"""

import os
import re
import errno
import logging
from getpass import getpass
from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol
from ..enumerate import WinrmClient, create_winrm_client, \
    create_parser_and_factory, ChainingProtocol, ParserFeedingProtocol

logging.basicConfig(level=logging.INFO)

HOSTNAME = 'oakland'
AUTH_TYPE = 'basic'
USERNAME = 'Administrator'
PASSWORD = None

CIM_CLASSES = [
    'Win32_LogicalDisk',
    'Win32_Volume',
    'Win32_OperatingSystem',
    'Win32_SystemEnclosure',
    'Win32_ComputerSystem',
    'Win32_Service',
    'Win32_IP4RouteTable',
    'Win32_NetworkAdapterConfiguration',
    'Win32_PerfRawData_Tcpip_NetworkInterface',
    'Win32_Processor',
    'Win32_Process',
    'Win32_PerfRawData_PerfDisk_PhysicalDisk',
    'Win32_PerfRawData_PerfProc_Process',
    'Win32_Product',
]


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST \
                or not os.path.isdir(path):
            raise


def find_required_properties(items):
    required_props = set(vars(items[0]).keys())
    for item in items[1:]:
        required_props &= set(vars(item).keys())
    return required_props


class WriteXmlToFileProtocol(Protocol):

    def __init__(self, file_):
        self.d = defer.Deferred()
        self._file = file_

    def dataReceived(self, data):
        self._file.write(data)

    def connectionLost(self, reason):
        self._file.close()
        self.d.callback(None)


class WriteXmlToFileHandler(object):

    def __init__(self, dirname, cim_class, suffix):
        self._dirname = dirname
        self._cim_class = cim_class
        self._suffix = suffix
        self._response_count = 0

    @defer.inlineCallbacks
    def handle_response(self, response):
        filename = '{0}_{1}_{2:03}.xml'.format(self._cim_class, self._suffix,
                                               self._response_count)
        self._response_count += 1
        f = open(os.path.join(self._dirname, filename), 'w')
        parser, factory = create_parser_and_factory()
        reader = ChainingProtocol([WriteXmlToFileProtocol(f),
                                   ParserFeedingProtocol(parser)])
        response.deliverBody(reader)
        yield reader.d
        defer.returnValue((factory.enumeration_context, factory.items))


@defer.inlineCallbacks
def do_enumerate(dirname, cim_class, props, query_type):
    wql = 'select {0} from {1}'.format(props, cim_class)
    handler = WriteXmlToFileHandler(dirname, cim_class, query_type)
    client = WinrmClient(HOSTNAME, AUTH_TYPE, USERNAME, PASSWORD, handler)
    items = yield client.enumerate(wql)
    defer.returnValue(items)


@defer.inlineCallbacks
def get_subdirname():
    client = create_winrm_client(HOSTNAME, AUTH_TYPE, USERNAME, PASSWORD)
    wql = 'select Caption from Win32_OperatingSystem'
    items = yield client.enumerate(wql)
    match = re.search(r'(2003|2008|2012)', items[0].Caption)
    defer.returnValue('server_{0}'.format(match.group(1)))


@defer.inlineCallbacks
def fetch():
    subdirname = yield get_subdirname()
    basedir = os.path.dirname(os.path.abspath(__file__))
    dirname = os.path.join(basedir, 'data', subdirname)
    mkdir_p(dirname)
    for cim_class in CIM_CLASSES:
        items = yield do_enumerate(dirname, cim_class, '*', 'star')
        required_properties = find_required_properties(items)
        filename = '{0}.properties'.format(cim_class)
        with open(os.path.join(dirname, filename), 'w') as f:
            for prop in required_properties:
                f.write(prop + '\n')
        props = ','.join(required_properties)
        yield do_enumerate(dirname, cim_class, props, 'all')
    reactor.stop()


def main():
    global PASSWORD
    PASSWORD = getpass()
    reactor.callWhenRunning(fetch)
    reactor.run()

if __name__ == '__main__':
    main()
