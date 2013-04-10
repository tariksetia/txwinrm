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
from ..response import create_parser_and_factory, ChainingProtocol, \
    ParserFeedingProtocol

logging.basicConfig(level=logging.INFO)

HOSTNAME = 'oakland'
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


class SingleValueAccumulator(object):

    def __init__(self):
        self.value = None

    def new_instance(self):
        pass

    def add_property(self, name, value):
        self.value = value


class PropertiesAccumulator(object):

    def __init__(self):
        self._instance_props = []

    @property
    def properties(self):
        required_props = self._instance_props[0]
        for instance_props in self._instance_props[1:]:
            required_props &= instance_props
        return required_props

    def new_instance(self):
        self._instance_props.append(set())

    def add_property(self, name, value):
        self._instance_props[-1].add(name)


class DoNothingAccumulator(object):

    def new_instance(self):
        pass

    def add_property(self, name, value):
        pass


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
    def handle_response(self, response, accumulator):
        filename = '{0}_{1}_{2:03}.xml'.format(self._cim_class, self._suffix,
                                               self._response_count)
        self._response_count += 1
        f = open(os.path.join(self._dirname, filename), 'w')
        parser, factory = create_parser_and_factory(accumulator)
        reader = ChainingProtocol([WriteXmlToFileProtocol(f),
                                   ParserFeedingProtocol(parser)])
        response.deliverBody(reader)
        yield reader.d
        defer.returnValue(factory.enumeration_context)


@defer.inlineCallbacks
def do_enumerate(factory, dirname, cim_class, props, query_type, accumulator):
    wql = 'select {0} from {1}'.format(props, cim_class)
    handler = WriteXmlToFileHandler(dirname, cim_class, query_type)
    client = factory.create_winrm_client_with_handler(handler)
    yield client.enumerate(HOSTNAME, USERNAME, PASSWORD, wql, accumulator)


@defer.inlineCallbacks
def get_subdirname(factory):
    client = factory.create_winrm_client()
    wql = 'select caption from Win32_OperatingSystem'
    accumulator = SingleValueAccumulator()
    yield client.enumerate(HOSTNAME, USERNAME, PASSWORD, wql, accumulator)
    match = re.search(r'(2003|2008|2012)', accumulator.value)
    defer.returnValue('server_{0}'.format(match.group(1)))


@defer.inlineCallbacks
def fetch():
    factory = WinrmClientFactory()
    subdirname = yield get_subdirname(factory)
    basedir = os.path.dirname(os.path.abspath(__file__))
    dirname = os.path.join(basedir, 'data', subdirname)
    mkdir_p(dirname)
    for cim_class in CIM_CLASSES:
        accumulator = PropertiesAccumulator()
        yield do_enumerate(factory, dirname, cim_class, '*', 'star',
                           accumulator)
        filename = '{0}.properties'.format(cim_class)
        with open(os.path.join(dirname, filename), 'w') as f:
            for prop in accumulator.properties:
                f.write(prop + '\n')
        props = ','.join(accumulator.properties)
        yield do_enumerate(factory, dirname, cim_class, props, 'all',
                           DoNothingAccumulator())
    reactor.stop()


def main():
    reactor.callWhenRunning(fetch)
    reactor.run()

if __name__ == '__main__':
    main()
