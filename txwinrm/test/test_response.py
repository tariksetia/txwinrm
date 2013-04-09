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

import os
import re
import unittest
from pprint import pformat
from ..response import create_parser_and_factory

MAX_RESPONSE_FILES = 999

INCOMPARABLE_PROPERTIES = dict(
    Win32_Process=[
        'KernelModeTime',
        'HandleCount',
        'PageFaults',
        'OtherOperationCount',
        'OtherTransferCount',
        'PrivatePageCount',
        'WorkingSetSize',
        'PageFileUsage',
        'UserModeTime',
        'PeakWorkingSetSize',
        'VirtualSize',
        'QuotaPagedPoolUsage',
        'ThreadCount',
        'QuotaNonPagedPoolUsage'],
    Win32_Processor=[
        'LoadPercentage'],
    Win32_IP4RouteTable=[
        'Age'],
    Win32_PerfRawData_PerfDisk_PhysicalDisk=[
        'PercentDiskReadTime_Base',
        'PercentDiskTime_Base',
        'PercentDiskWriteTime_Base',
        'PercentIdleTime',
        'PercentIdleTime_Base',
        'Timestamp_PerfTime',
        'Timestamp_Sys100NS',
        'DiskBytesPersec',
        'AvgDisksecPerTransfer_Base',
        'AvgDiskBytesPerTransfer',
        'AvgDiskQueueLength',
        'DiskWriteBytesPersec',
        'AvgDiskBytesPerTransfer_Base',
        'DiskWritesPersec',
        'PercentDiskTime',
        'AvgDiskBytesPerWrite',
        'AvgDiskBytesPerWrite_Base',
        'AvgDisksecPerWrite',
        'PercentDiskWriteTime',
        'SplitIOPerSec',
        'AvgDiskWriteQueueLength',
        'AvgDisksecPerTransfer',
        'DiskTransfersPersec',
        'AvgDisksecPerWrite_Base'],
    Win32_OperatingSystem=[
        'FreePhysicalMemory',
        'FreeVirtualMemory'],
    Win32_PerfRawData_PerfProc_Process=[
        'PercentPrivilegedTime',
        'PercentProcessorTime',
        'Timestamp_Object',
        'Timestamp_PerfTime',
        'Timestamp_Sys100NS',
        'HandleCount',
        'PageFaultsPersec',
        'IOOtherOperationsPersec',
        'PercentUserTime',
        'WorkingSet',
        'WorkingSetPrivate',
        'IOOtherBytesPersec',
        'PoolNonpagedBytes',
        'PageFileBytesPeak',
        'VirtualBytes',
        'WorkingSetPeak',
        'PageFileBytes',
        'PrivateBytes',
        'VirtualBytesPeak',
        'ElapsedTime'],
    Win32_PerfRawData_Tcpip_NetworkInterface=[
        'BytesReceivedPersec',
        'BytesSentPersec',
        'BytesTotalPersec',
        'PacketsPersec',
        'PacketsReceivedPersec',
        'PacketsReceivedUnicastPersec',
        'PacketsSentPersec',
        'PacketsSentUnicastPersec',
        'Timestamp_PerfTime',
        'Timestamp_Sys100NS'])


class Result(object):

    def __init__(self, cim_class, props):
        self.cim_class = cim_class
        self.props = props

    def __eq__(self, other):
        retval = True
        for name in vars(other):
            if name not in vars(self):
                if name not in self.props:
                    continue
                print "self missing", name
                return False
        for name, value in vars(self).iteritems():
            if name not in vars(other):
                if name not in self.props:
                    continue
                print "other missing", name
                return False
            if vars(other)[name] != value:
                if self.cim_class in INCOMPARABLE_PROPERTIES \
                        and name in INCOMPARABLE_PROPERTIES[self.cim_class]:
                    continue
                print '{0} {1}: "{2}" {3} != "{4}" {5}' \
                      .format(self.cim_class, name, self.Name, value,
                              other.Name, vars(other)[name])
                retval = False
        return retval

    def __repr__(self):
        return '\n' + pformat(vars(self), indent=4)


class MyTestAccumulator(object):

    def __init__(self, cim_class, props):
        self.cim_class = cim_class
        self.props = props
        self.results = []

    def new_instance(self):
        self.results.append(Result(self.cim_class, self.props))

    def add_property(self, name, value):
        setattr(self.results[-1], name, value)


class TestWinrm(unittest.TestCase):

    def setUp(self):
        # self.maxDiff = None
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
        data_by_os_version = get_data_by_os_version()
        for os_version, data_by_cim_class in data_by_os_version.iteritems():
            for cim_class, data in data_by_cim_class.iteritems():
                star_results = get_results(cim_class, data['properties'],
                                           data['star'])
                all_results = get_results(cim_class, data['properties'],
                                          data['all'])
                self.assertEqual(star_results, all_results)
                for results in star_results, all_results:
                    for result in results:
                        for prop in data['properties']:
                            self.assertIn(prop, vars(result))


def get_results(cim_class, props, xml_texts):
    results = []
    for xml_text in xml_texts:
        accumulator = MyTestAccumulator(cim_class, props)
        parser, factory = create_parser_and_factory(accumulator)
        parser.feed(xml_text)
        results.extend(accumulator.results)
    return results


def chop_none_terminated_list(xs):
    return xs[:xs.index(None)]


def get_data_by_os_version():
    """
    {'server_2008': {'Win32_ComputerSystem': {'all': [<XML texts>]
                                             {'star': [<XML texts>]
                                             {'properties': [<property names>]
    """
    basedir = os.path.dirname(os.path.abspath(__file__))
    datadir = os.path.join(basedir, "data")
    data_by_os_version = {}
    for root, dirnames, filenames in os.walk(datadir):
        if root == datadir:
            continue
        os_version = os.path.split(root)[-1]
        data_by_os_version[os_version] = data_by_cim_class = {}
        for filename in filenames:
            with open(os.path.join(root, filename)) as f:
                text = f.read()
                if filename.endswith('.properties'):
                    cim_class = filename.split('.')[0]
                    if cim_class not in data_by_cim_class:
                        data_by_cim_class[cim_class] = {}
                    data_by_cim_class[cim_class]['properties'] = \
                        text.splitlines()
                    continue
                if '_star_' in filename:
                    query_type = 'star'
                    cim_class = filename[:-len('_star_NNN.xml')]
                elif '_all_' in filename:
                    query_type = 'all'
                    cim_class = filename[:-len('_all_NNN.xml')]
                else:
                    raise Exception('unknown query type for file {0}'
                                    .format(filename))
                if cim_class not in data_by_cim_class:
                    data_by_cim_class[cim_class] = {}
                if query_type not in data_by_cim_class[cim_class]:
                    data_by_cim_class[cim_class][query_type] = \
                        [None] * MAX_RESPONSE_FILES
                i = int(re.search(r'(\d{3})', filename).group(1))
                if i > MAX_RESPONSE_FILES:
                    raise Exception('Too many response files: {0} Max is {1}'
                                    .format(filename, MAX_RESPONSE_FILES))
                data_by_cim_class[cim_class][query_type][i] = text
        for cim_class, data in data_by_cim_class.iteritems():
            data['star'] = chop_none_terminated_list(data['star'])
            data['all'] = chop_none_terminated_list(data['all'])

    return data_by_os_version

if __name__ == '__main__':
    unittest.main()
