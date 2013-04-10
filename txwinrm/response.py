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
from . import constants as c

log = logging.getLogger('zen.winrm')


def create_parser_and_factory(accumulator):
    parser = sax.make_parser()
    parser.setFeature(sax.handler.feature_namespaces, True)
    text_buffer = TextBufferingContentHandler()
    factory = EnvelopeHandlerFactory(text_buffer, accumulator)
    content_handler = ChainingContentHandler([
        text_buffer,
        DispatchingContentHandler(factory)])
    parser.setContentHandler(content_handler)
    return parser, factory


class SaxResponseHandler(object):

    @defer.inlineCallbacks
    def handle_response(self, response, accumulator):
        parser, factory = create_parser_and_factory(accumulator)
        reader = ParserFeedingProtocol(parser)
        response.deliverBody(reader)
        yield reader.d
        defer.returnValue(factory.enumeration_context)


def safe_lower_equals(left, right):
    left_l, right_l = [None if s is None else s.lower() for s in left, right]
    return left_l == right_l


class TagComparer(object):

    def __init__(self, uri, localname):
        self.uri = uri
        self.localname = localname

    def matches(self, uri, localname):
        return safe_lower_equals(self.uri, uri) \
            and safe_lower_equals(self.localname, localname)

    def __repr__(self):
        return str((self.uri, self.localname))


def create_tag_comparer(name):
    uri, localname = name
    return TagComparer(uri, localname)


class ChainingProtocol(Protocol):

    def __init__(self, chain):
        self._chain = chain
        self.d = defer.DeferredList([p.d for p in chain])

    def dataReceived(self, data):
        for protocol in self._chain:
            protocol.dataReceived(data)

    def connectionLost(self, reason):
        for protocol in self._chain:
            protocol.connectionLost(reason)


class ParserFeedingProtocol(Protocol):

    def __init__(self, xml_parser):
        self._xml_parser = xml_parser
        self.d = defer.Deferred()
        self._debug_data = ''

    def dataReceived(self, data):
        if log.isEnabledFor(logging.DEBUG):
            self._debug_data += data
            log.debug("ParserFeedingProtocol dataReceived {0}"
                      .format(data))
        self._xml_parser.feed(data)

    def connectionLost(self, reason):
        if self._debug_data and log.isEnabledFor(logging.DEBUG):
            try:
                import xml.dom.minidom
                xml = xml.dom.minidom.parseString(self._debug_data)
                log.debug(xml.toprettyxml())
            except:
                log.debug('Could not prettify response XML: "{0}"'
                          .format(self._debug_data))
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

    def characters(self, content):
        for handler in self._chain:
            handler.characters(content)


class TextBufferingContentHandler(sax.handler.ContentHandler):

    def __init__(self):
        self._buffer = StringIO()
        self._text = None

    @property
    def text(self):
        return self._text

    def endElementNS(self, name, qname):
        self._text = self._buffer.getvalue()
        self._buffer.reset()
        self._buffer.truncate()

    def characters(self, content):
        self._buffer.write(content)


class DispatchingContentHandler(sax.handler.ContentHandler):

    def __init__(self, subhandler_factory):
        self._subhandler_factory = subhandler_factory
        self._subhandler_tag = None
        self._subhandler = None

    def startElementNS(self, name, qname, attrs):
        log.debug('DispatchingContentHandler startElementNS {0} {1} {2}'
                  .format(name, self._subhandler, self._subhandler_tag))
        if self._subhandler is None:
            self._subhandler, tag = self._get_subhandler_for(name)
            if self._subhandler is not None:
                self._subhandler_tag = tag
                log.debug('new subhandler {0} {1}'
                          .format(self._subhandler, self._subhandler_tag))

        if self._subhandler is not None:
            self._subhandler.startElementNS(name, qname, attrs)

    def endElementNS(self, name, qname):
        log.debug('DispatchingContentHandler endElementNS {0} {1}'
                  .format(name, self._subhandler))
        if self._subhandler is not None:
            self._subhandler.endElementNS(name, qname)
        if self._subhandler_tag is not None:
            uri, localname = name
            if self._subhandler_tag.matches(uri, localname):
                self._subhandler_tag = None
                self._subhandler = None
                log.debug('removed subhandler')

    def _get_subhandler_for(self, name):
        tag = create_tag_comparer(name)
        return self._subhandler_factory.get_handler_for(tag), tag


class EnvelopeHandlerFactory(object):

    def __init__(self, text_buffer, accumulator):
        self._enumerate = EnumerateContentHandler(text_buffer)
        self._items = ItemsContentHandler(text_buffer, accumulator)

    @property
    def enumeration_context(self):
        return self._enumerate.enumeration_context

    def get_handler_for(self, tag):
        handler = None
        if tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_ENUMERATION_CONTEXT) \
                or tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_END_OF_SEQUENCE):
            handler = self._enumerate
        elif tag.matches(c.XML_NS_WS_MAN, c.WSENUM_ITEMS) \
                or tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_ITEMS):
            handler = self._items
        log.debug('EnvelopeHandlerFactory get_handler_for {0} {1}'
                  .format(tag, handler))
        return handler


class EnumerateContentHandler(sax.handler.ContentHandler):

    def __init__(self, text_buffer):
        self._text_buffer = text_buffer
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

    def __init__(self, text_buffer, accumulator):
        self._text_buffer = text_buffer
        self._accumulator = accumulator
        self._tag_stack = deque()
        self._value = None

    def startElementNS(self, name, qname, attrs):
        log.debug('ItemsContentHandler startElementNS {0} v="{1}" t="{2}" {3}'
                  .format(name, self._value, self._text_buffer.text,
                          self._tag_stack))
        tag = create_tag_comparer(name)
        if len(self._tag_stack) > 3:
            raise Exception("tag stack too long: {0} {1}"
                            .format([t.localname for t in self._tag_stack],
                                    tag.localname))
        if len(self._tag_stack) == 1:
            self._accumulator.new_instance()
        elif len(self._tag_stack) == 2:
            if attrs.get((c.XML_NS_BUILTIN, c.BUILTIN_NIL), None) == 'true':
                self._value = (None,)
        self._tag_stack.append(tag)

    def endElementNS(self, name, qname):
        log.debug('ItemsContentHandler endElementNS {0} v="{1}" t="{2}" {3}'
                  .format(name, self._value, self._text_buffer.text,
                          self._tag_stack))
        tag = create_tag_comparer(name)
        popped_tag = self._tag_stack.pop()
        if not popped_tag.matches(tag.uri, tag.localname):
            raise Exception("End of {0} when expecting {1}"
                            .format(tag.localname, popped_tag.localname))
        log.debug("ItemsContentHandler endElementNS tag_stack: {0}"
                  .format(self._tag_stack))
        if len(self._tag_stack) == 2:
            if self._value is None:
                value = self._text_buffer.text
            else:
                value = self._value[0]
            self._accumulator.add_property(tag.localname, value)
            self._value = None
        elif len(self._tag_stack) == 3:
            if tag.matches(c.XML_NS_CIM_SCHEMA, "Datetime") \
                    or tag.matches(None, "Datetime"):
                self._value = (get_datetime(self._text_buffer.text),)


def get_datetime(text):
    text = text.strip()
    if '.' in text:
        format = "%Y-%m-%dT%H:%M:%S.%fZ"
    else:
        format = "%Y-%m-%dT%H:%M:%SZ"
    return datetime.strptime(text, format)
