##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

"""
This testing requires real Windows machines that are setup manually.
"""

import os
import re
import unittest
from itertools import izip
from xml import sax
from datetime import datetime
from ..enumerate import create_parser_and_factory, \
    ItemsContentHandler, ChainingContentHandler, TextBufferingContentHandler, \
    ItemsAccumulator, AddPropertyWithoutItemError, Item, TagStackStateError, \
    TagComparer

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
        'QuotaNonPagedPoolUsage',
        'WriteTransferCount',
        'WriteOperationCount',
        'ReadOperationCount',
        'ReadTransferCount',
        'PeakPageFileUsage',
        'PeakVirtualSize',
        'QuotaPeakPagedPoolUsage',
        'QuotaPeakNonPagedPoolUsage'],
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
        'AvgDisksecPerWrite_Base',
        'AvgDiskBytesPerRead',
        'AvgDisksecPerRead',
        'CurrentDiskQueueLength',
        'DiskReadBytesPersec',
        'AvgDisksecPerRead_Base',
        'AvgDiskBytesPerRead_Base',
        'AvgDiskReadQueueLength',
        'PercentDiskReadTime',
        'DiskReadsPersec'],
    Win32_OperatingSystem=[
        'FreePhysicalMemory',
        'FreeVirtualMemory',
        'LocalDateTime'],
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
        'ElapsedTime',
        'IOWriteBytesPersec',
        'IOWriteOperationsPersec',
        'IODataBytesPersec',
        'IODataOperationsPersec',
        'ThreadCount',
        'IOReadBytesPersec',
        'IOReadOperationsPersec',
        'PoolPagedBytes'],
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


def _is_missing(item, other_props, required_props, item_label):
    for prop in other_props:
        if prop not in vars(item):
            if prop not in required_props:
                continue
            print item_label, "missing", prop
            return True
    return False


def _are_values_equal(left, right, prop, cim_class):
    if prop not in vars(left) or prop not in vars(right):
        return True
    l_value = vars(left).get(prop)
    r_value = vars(right).get(prop)
    retval = l_value == r_value
    if not retval:
        print '{0} {1}: "{2}" {3} != "{4}" {5}' .format(
            cim_class, prop, left.Name, l_value, right.Name, r_value)
    return retval


def are_items_equal(left, right, cim_class, required_props):
    retval = True
    if _is_missing(left, vars(right).keys(), required_props, 'left'):
        return False
    if _is_missing(right, vars(left).keys(), required_props, 'right'):
        return False
    for prop in vars(left):
        if cim_class in INCOMPARABLE_PROPERTIES \
                and prop in INCOMPARABLE_PROPERTIES[cim_class]:
            continue
        if not _are_values_equal(left, right, prop, cim_class):
            retval = False
    return retval


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
        the CIM class as the item element's tag and as the namespace for
        the tags of each field. WQL queries that specify fields use XmlFragment
        as the item element's tag and do not use a namespace for the tags
        of each field.The client should normalize both response types so the
        item is guaranteed to be consistent before further operations are
        performed on it. This test goes through a list of queries that
        explicitly list all fields for the CIM class. It runs the queries on
        each know host along with a 'select *' query and verifies that the
        items match.
        """
        data_by_os_version = get_data_by_os_version()
        for os_version, data_by_cim_class in data_by_os_version.iteritems():
            for cim_class, data in data_by_cim_class.iteritems():
                star_items = self._get_items(data['star'])
                all_items = self._get_items(data['all'])
                self.assertEqual(len(star_items), len(all_items))
                for star_item, all_item in izip(star_items, all_items):
                    are_items_equal(
                        star_item, all_item, cim_class, data['properties'])
                for items in star_items, all_items:
                    for item in items:
                        for prop in data['properties']:
                            self.assertIn(prop, vars(item))

    def _get_items(self, xml_texts):
        enumeration_contexts, items = \
            get_enumeration_contexts_and_items(xml_texts)
        self.assertEqual(len(enumeration_contexts), len(xml_texts))
        for enumeration_context in enumeration_contexts[:-1]:
            self.assertIsNotNone(enumeration_context)
        self.assertIsNone(enumeration_contexts[-1])
        return items


def get_enumeration_contexts_and_items(xml_texts):
    enumeration_contexts = []
    items = []
    for xml_text in xml_texts:
        parser, factory = create_parser_and_factory()
        parser.feed(xml_text)
        enumeration_contexts.append(factory.enumeration_context)
        items.extend(factory.items)
    return enumeration_contexts, items


def chop_none_terminated_list(xs):
    return xs[:xs.index(None)]


def _get_cim_class_and_query_type(filename):
    if '_star_' in filename:
        cim_class = filename[:-len('_star_NNN.xml')]
        query_type = 'star'
    elif '_all_' in filename:
        cim_class = filename[:-len('_all_NNN.xml')]
        query_type = 'all'
    else:
        raise Exception('unknown query type for file {0}'
                        .format(filename))
    return cim_class, query_type


def _get_index(filename):
    i = int(re.search(r'(\d{3})', filename).group(1))
    if i > MAX_RESPONSE_FILES:
        raise Exception('Too many response files: {0} Max is {1}'
                        .format(filename, MAX_RESPONSE_FILES))
    return i


def _get_data_by_cim_class(root, filenames):
    data_by_cim_class = {}
    for filename in filenames:
        with open(os.path.join(root, filename)) as f:
            text = f.read()
        if filename.endswith('.properties'):
            cim_class = filename.split('.')[0]
            if cim_class not in data_by_cim_class:
                data_by_cim_class[cim_class] = {}
            data_by_cim_class[cim_class]['properties'] = text.splitlines()
            continue
        cim_class, query_type = _get_cim_class_and_query_type(filename)
        if cim_class not in data_by_cim_class:
            data_by_cim_class[cim_class] = {}
        if query_type not in data_by_cim_class[cim_class]:
            data_by_cim_class[cim_class][query_type] = \
                [None] * MAX_RESPONSE_FILES
        index = _get_index(filename)
        data_by_cim_class[cim_class][query_type][index] = text
    return data_by_cim_class


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
        data_by_os_version[os_version] = \
            _get_data_by_cim_class(root, filenames)
        for cim_class, data in data_by_os_version[os_version].iteritems():
            data['star'] = chop_none_terminated_list(data['star'])
            data['all'] = chop_none_terminated_list(data['all'])

    return data_by_os_version

CIM_CLASS_FMT = """
<w:Items xmlns:w="http://schemas.dmtf.org/wbem/wsman/1/wsman.xsd"
xmlns:p="http://schemas.microsoft.com/wbem/wsman/1/wmi/root/cimv2/{cim_class}">
<p:{cim_class}>
{properties}
</p:{cim_class}>
</w:Items>
"""

XML_FRAGMENT_FMT = """
<n:Items xmlns:n="http://schemas.xmlsoap.org/ws/2004/09/enumeration"
         xmlns:w="http://schemas.dmtf.org/wbem/wsman/1/wsman.xsd">
<w:XmlFragment>
{properties}
</w:XmlFragment>
</n:Items>
"""

DATETIME_CIM_CLASS = """
<p:InstallDate xmlns:cim="http://schemas.dmtf.org/wbem/wscim/1/common">
<cim:Datetime>2013-03-09T03:06:25Z</cim:Datetime>
</p:InstallDate>
"""

DATETIME_XML_FRAGMENT = """
<CreationDate>
<Datetime>2013-04-09T15:42:20.4124Z</Datetime>
</CreationDate>
"""

NIL_CIM_CLASS = """
<p:Caption xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:nil="true"/>
"""

NIL_XML_FRAGMENT = """
<Access xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:nil="true"/>
"""

EMPTY_CIM_CLASS = """
<p:Version></p:Version>
"""

EMPTY_XML_FRAGMENT = """
<Version></Version>
"""

ARRAY_CIM_CLASS = """
<p:Roles>LM_Workstation</p:Roles>
<p:Roles>LM_Server</p:Roles>
<p:Roles>NT</p:Roles>
<p:Roles>Server_NT</p:Roles>
"""

ARRAY_XML_FRAGMENT = """
<Roles>LM_Workstation</Roles>
<Roles>LM_Server</Roles>
<Roles>NT</Roles>
<Roles>Server_NT</Roles>
"""

TOO_DEEP = """
<foo>
<bar>
<quux>
</quux>
</bar>
</foo>
"""


def parse_xml_str(xml_str):
    parser = sax.make_parser()
    parser.setFeature(sax.handler.feature_namespaces, True)
    text_buffer = TextBufferingContentHandler()
    items_handler = ItemsContentHandler(text_buffer)
    content_handler = ChainingContentHandler([text_buffer, items_handler])
    parser.setContentHandler(content_handler)
    parser.feed(xml_str)
    return items_handler.items


class TestDataType(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def _do_test_of_prop_parsing(self, data):
        for xml_str, prop, expected in data:
            items = parse_xml_str(xml_str)
            self.assertEqual(len(items), 1)
            actual = getattr(items[0], prop)
            self.assertEqual(actual, expected)

    def test_items_with_datetime(self):
        datetime_1 = CIM_CLASS_FMT.format(cim_class='Win32_OperatingSystem',
                                          properties=DATETIME_CIM_CLASS)
        datetime_2 = XML_FRAGMENT_FMT.format(properties=DATETIME_XML_FRAGMENT)
        data = [(datetime_1, "InstallDate",
                 datetime(2013, 3, 9, 03, 06, 25)),
                (datetime_2, "CreationDate",
                 datetime(2013, 4, 9, 15, 42, 20, 412400))]
        self._do_test_of_prop_parsing(data)

    def test_nil(self):
        nil_1 = CIM_CLASS_FMT.format(
            cim_class="Win32_PerfRawData_Tcpip_NetworkInterface",
            properties=NIL_CIM_CLASS)
        nil_2 = XML_FRAGMENT_FMT.format(properties=NIL_XML_FRAGMENT)
        data = [(nil_1, "Caption", None),
                (nil_2, "Access", None)]
        self._do_test_of_prop_parsing(data)

    def test_empty(self):
        empty_1 = CIM_CLASS_FMT.format(cim_class="Win32_Processor",
                                       properties=EMPTY_CIM_CLASS)
        empty_2 = XML_FRAGMENT_FMT.format(properties=EMPTY_XML_FRAGMENT)
        data = [(empty_1, "Version", ""), (empty_2, "Version", "")]
        self._do_test_of_prop_parsing(data)

    def test_array(self):
        array_1 = CIM_CLASS_FMT.format(cim_class="Win32_ComputerSystem",
                                       properties=ARRAY_CIM_CLASS)
        array_2 = XML_FRAGMENT_FMT.format(properties=ARRAY_XML_FRAGMENT)
        prop = "Roles"
        expected = ["LM_Workstation", "LM_Server", "NT", "Server_NT"]
        data = [(array_1, prop, expected), (array_2, prop, expected)]
        self._do_test_of_prop_parsing(data)

    def test_too_deep(self):
        xml_str = CIM_CLASS_FMT.format(cim_class="Win32_Blah",
                                       properties=TOO_DEEP)
        self.assertRaises(Exception, parse_xml_str, xml_str)

    def test_tag_stack_state_error(self):
        parser = sax.make_parser()
        parser.setFeature(sax.handler.feature_namespaces, True)
        text_buffer = TextBufferingContentHandler()
        items_handler = ItemsContentHandler(text_buffer)
        content_handler = ChainingContentHandler([text_buffer, items_handler])
        parser.setContentHandler(content_handler)
        xml1 = '<n:Items ' \
               'xmlns:n="http://schemas.xmlsoap.org/ws/2004/09/enumeration" ' \
               'xmlns:w="http://schemas.dmtf.org/wbem/wsman/1/wsman.xsd">' \
               '<w:XmlFragment>'
        parser.feed(xml1)
        tag = TagComparer(None, 'foo')
        items_handler._tag_stack.append(tag)
        xml2 = "</w:XmlFragment></n:Items>"
        self.assertRaises(TagStackStateError, parser.feed, xml2)


class TestItemsAccumulator(unittest.TestCase):

    def test_add_property_without_item(self):
        self.assertRaises(AddPropertyWithoutItemError,
                          ItemsAccumulator().add_property, "foo", "bar")


class TestItem(unittest.TestCase):

    def test_repr(self):
        item = Item()
        self.assertEqual(repr(item), '\n{   }')

if __name__ == '__main__':
    unittest.main()
    # suite = unittest.TestLoader().loadTestsFromTestCase(TestDataType)
    # unittest.TextTestRunner().run(suite)
