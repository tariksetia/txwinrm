##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
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
from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol
from ..client import WinrmClientFactory

logging.basicConfig()
logger = logging.getLogger()

HOSTNAME = 'gilroy'
USERNAME = 'Administrator'
PASSWORD = 'Z3n0ss'

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
    'Win32_CacheMemory',
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


class CaptionAccumulator(object):

    def __init__(self):
        self.caption = None

    def new_instance(self):
        pass

    def append_element(self, uri, localname, text):
        self.caption = text


class PropertiesAccumulator(object):

    def __init__(self):
        self.properties = set([])

    def new_instance(self):
        pass

    def append_element(self, uri, localname, text):
        self.properties.add(localname)


class WriteXmlToFileProtocol(Protocol):

    def __init__(self, file_):
        self._file = file_

    def dataReceived(self, data):
        self._file.write(data)

    def connectionLost(self, reason):
        self._file.close()


class WriteXmlToFileHandler(object):

    def __init__(self, dirname):
        self._dirname = dirname
        self.suffix = None

    def handle_response(self, response, resource_uri, cim_class, accumulator):
        filename = '{0}_{1}.xml'.format(cim_class, self.suffix)
        f = open(os.path.join(self._dirname, filename), 'w+')
        reader = WriteXmlToFileProtocol(f)
        response.deliverBody(reader)


@defer.inlineCallbacks
def get_subdirname(client):
    wql = 'select caption from Win32_OperatingSystem'
    accumulator = CaptionAccumulator()
    yield client.enumerate(HOSTNAME, USERNAME, PASSWORD, wql, accumulator)
    match = re.search(r'(2003|2008|2012)', accumulator.caption)
    defer.returnValue('server_{0}'.format(match.group(1)))


@defer.inlineCallbacks
def fetch():
    factory = WinrmClientFactory(logger)
    client = factory.create_winrm_client()
    subdirname = yield get_subdirname(client)
    basedir = os.path.dirname(os.path.abspath(__file__))
    dirname = os.path.join(basedir, 'data', subdirname)
    mkdir_p(dirname)
    handler = WriteXmlToFileHandler(dirname)
    write_client = factory.create_winrm_client_with_handler(handler)
    for cim_class in CIM_CLASSES:
        wql = 'select * from {0}'.format(cim_class)
        handler.suffix = 'star'
        yield write_client.enumerate(HOSTNAME, USERNAME, PASSWORD, wql, None)
        accumulator = PropertiesAccumulator()
        yield client.enumerate(HOSTNAME, USERNAME, PASSWORD, wql, accumulator)
        filename = '{0}.properties'.format(cim_class)
        with open(os.path.join(dirname, filename), 'w+') as f:
            for prop in accumulator.properties:
                f.write(prop)
        explicit_wql = 'select {0} from {1}'.format(
            ','.join(accumulator.properties),
            cim_class)
        handler.suffix = 'all'
        yield write_client.enumerate(HOSTNAME, USERNAME, PASSWORD,
                                     explicit_wql, None)
    reactor.stop()


def main():
    reactor.callWhenRunning(fetch)
    reactor.run()

if __name__ == '__main__':
    main()
