##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""WinRM response handlers. Parses the SOAP XML responses from WinRM service.
"""

import logging
from cStringIO import StringIO
from datetime import datetime
from collections import deque
from xml import sax
from twisted.internet import defer
from twisted.internet.protocol import Protocol
from twisted.web._newclient import ResponseFailed
from . import contstants as c

log = logging.getLogger('zen.winrm')


class SaxResponseHandler(object):

    def __init__(self):
        self._parser = sax.make_parser()
        self._parser.setFeature(sax.handler.feature_namespaces, True)

    @defer.inlineCallbacks
    def handle_response(self, response, accumulator):
        text_buffer = TextBufferingContentHandler()
        handler = ChainingContentHandler([
            text_buffer,
            DispatchingContentHandler(EnvelopeHandlerFactory(text_buffer)),
        ])
        self._parser.setContentHandler(handler)
        reader = ParserFeedingProtocol(self._parser)
        response.deliverBody(reader)
        yield reader.d
        defer.returnValue(self._handler.enumeration_context)


class TagComparer(object):

    def __init__(self, uri, localname):
        self.uri = uri.lower()
        self.localname = localname.lower()

    def matches(self, uri, localname):
        return self.uri == uri.lower() \
            and self.localname == localname.lower()


def create_tag_comparer(name):
    uri, localname = name
    return TagComparer(uri, localname)


class ParserFeedingProtocol(Protocol):

    def __init__(self, xml_parser):
        self._xml_parser = xml_parser
        self.d = defer.Deferred()
        self._debug_data = ''

    def dataReceived(self, data):
        if log.isEnabledFor(logging.DEBUG):
            self._debug_data += data
        self._xml_parser.feed(data)

    def connectionLost(self, reason):
        if log.isEnabledFor(logging.DEBUG):
            import xml.dom.minidom
            xml = xml.dom.minidom.parseString(self._debug_data)
            log.debug(xml.toprettyxml())
        if isinstance(reason.value, ResponseFailed):
            log.error("Connection lost: {0}".format(reason.value.reasons[0]))
        self.d.callback(None)


class ChainingContentHandler(sax.handler.ContentHandler):

    def __init__(self, chain):
        self._chain = chain

    def startElementNS(self, name, qname, attrs):
        for handler in self._chain:
            handler.startElementNS(name, qname, attrs)

    def endElementNS(self, name, qname):
        for handler in self._chain:
            handler.endElementNS(name, qname)


class TextBufferingContentHandler(sax.handler.ContentHandler):

    def __init__(self, subhandler_factory):
        self._buffer = StringIO()
        self.text = None

    def endElementNS(self, name, qname):
        self.text = self._buffer.getvalue()
        self._buffer.reset()
        self._buffer.truncate()

    def characters(self, content):
        self._buffer.write(content)


class DispatchingContentHandler(sax.handler.ContentHandler):

    def __init__(self, subhandler_factory):
        self._subhandler_factory
        self._subhandler_tag = None
        self._subhandler = None

    def startElementNS(self, name, qname, attrs):
        if self._subhandler is not None:
            self._subhandler.startElementNS(name, qname, attrs)
        if self._subhandler is None:
            self._subhandler, tag = self._get_subhandler_for(name)
            if self._subhandler is not None:
                self._subhandler_tag = tag

    def endElementNS(self, name, qname):
        if self._subhandler_tag is not None:
            uri, localname = name
            if self._subhandler_tag.matches(uri, localname):
                self._subhandler_tag = None
                self._subhandler = None
        if self._subhandler is not None:
            self._subhandler.endElementNS(name, qname)

    def _get_subhandler_for(self, name):
        tag = create_tag_comparer(name)
        return self._subhandler_factory.get_handler_for(tag), tag


class EnvelopeHandlerFactory(object):

    def __init__(self, text_buffer):
        self._header_handler = HeaderContentHandler(text_buffer)
        self._items_handler = ItemsContentHandler(text_buffer)

    def get_handler_for(self, tag):
        if tag.matches(c.XML_NS_SOAP_1_2, c.SOAP_HEADER):
            return self._header_handler
        if tag.matches(c.XML_NS_WS_MAN, c.WSENUM_ITEMS) \
                or tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_ITEMS):
            return self._items_handler


class HeaderContentHandler(sax.handler.ContentHandler):

    def __init__(self, text_buffer):
        self._text_buffer
        self._enumeration_context = None
        self._end_of_sequence = False

    @property
    def enumeration_context(self):
        if not self._end_of_sequence:
            return self._enumeration_context

    def endElementNS(self, name, qname):
        tag = create_tag_comparer(name)
        if tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_ENUMERATION_CONTEXT):
            self._enumeration_context = self._text_buffer.text
        if tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_END_OF_SEQUENCE):
            self._end_of_sequence = True


class ItemsContentHandler(sax.handler.ContentHandler):

    def __init__(self, text_buffer):
        self._text_buffer = text_buffer
        self._nil = False
        self._tag_stack = deque()
        self._value = None

    def startElementNS(self, name, qname, attrs):
        if len(self._tag_stack) > 1:
            raise Exception("tag stack too long: {0}".format(self._tag_stack))
        tag = create_tag_comparer(name)
        self._tag_stack.append(tag)
        if not self._tag_stack:
            # instance
            pass
        elif len(self._tag_stack) == 1:
            # property
            pass
        elif len(self._tag_stack) == 2:
            # date
            pass
        else:
            

    def endElementNS(self, name, qname):
        tag = create_tag_comparer(name)
        popped_tag = self._tag_stack.pop()
        if not popped_tag.matches(tag.uri, tag.localname):
            raise Exception("End of {0} when expecting {1}"
                            .format(tag.localname, popped_tag.localname))

        if not self._tag_stack:
            # instance
            pass
        elif len(self._tag_stack) == 1:
            # property
            pass
        elif len(self._tag_stack) == 2:
            # date
            pass

        self._nil = False



if tag.matches(c.XML_NS_CIM_SCHEMA, "datetime"):
                if '.' in text:
                    format = "%Y-%m-%dT%H:%M:%S.%fZ"
                else:
                    format = "%Y-%m-%dT%H:%M:%SZ"
                date = datetime.strptime(text, format)





class WinrmContentHandler(object):

    def __init__(self):
        self._in_items = False
        self._property = None

    def startElementNS(self, name, qname, attrs):
        uri, localname, tag = self._element('start', name)
        if localname is None:
            return
        if not tag.matches(c.XML_NS_CIM_SCHEMA, "datetime"):
            self._property = localname

    def endElementNS(self, name, qname):
        uri, localname, tag = self._element('end', name)
        if localname is None:
            return
        if self._in_items:
            
                self._accumulator.append_element(uri, self._property, date)
                self._property = None
            elif self._property is not None:
                self._accumulator.append_element(uri, localname, text)
        else:
            self._tracker.append_element(uri, localname, text)


    def _element(self, event, name):
        uri, localname = name
        if uri is None:
            uri = ''
        tag = TagComparer(uri, localname)
        if tag.matches(c.XML_NS_WS_MAN, c.WSENUM_ITEMS) \
                or tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_ITEMS):
            self._in_items = event == 'start'
            return None, None, None
        if tag.matches(self._resource_uri, self._cim_class) \
                or tag.matches(c.XML_NS_WS_MAN, c.WSM_XML_FRAGMENT):
            if event == 'start':
                self._accumulator.new_instance()
            return None, None, None
        return uri, localname, tag
