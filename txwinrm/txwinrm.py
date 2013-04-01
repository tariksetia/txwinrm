#! /usr/bin/env python

##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Use twisted web client to enumerate/pull WQL query.



"""

import sys
import os
import base64
from argparse import ArgumentParser

from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers

from . import contstants as c
from . import response as r

GLOBAL_ELEMENT_COUNT = 0


def get_request_template(name):
    basedir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(basedir, 'request', name + '.xml')


class ElementPrinter(object):

    def __init__(self):
        self._elems_with_text = []
        self._longest_tag = 0
        self._enumeration_context = None
        self._end_of_sequence = False

    def new_instance(self):
        demarc = '-' * self._longest_tag
        self._elems_with_text.append((demarc, demarc))

    def append_element(self, uri, localname, text):
        global GLOBAL_ELEMENT_COUNT
        GLOBAL_ELEMENT_COUNT += 1
        tag = uri.split('/')[-1] + '.' + localname
        self._elems_with_text.append((tag, text))
        if len(tag) > self._longest_tag:
            self._longest_tag = len(tag)
        if uri == c.XML_NS_ENUMERATION:
            if localname == c.WSENUM_ENUMERATION_CONTEXT:
                self._enumeration_context = text
            elif localname == c.WSENUM_END_OF_SEQUENCE:
                self._end_of_sequence = True

    def print_elems_with_text(self):
        for tag, text in self._elems_with_text:
            print '{0:>{width}} {1}'.format(tag, text, width=self._longest_tag)

    @property
    def enumeration_context(self):
        if not self._end_of_sequence:
            return self._enumeration_context


class StringProducer(object):

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)


class ErrorReader(Protocol):

    def __init__(self, hostname, wql):
        self.d = defer.Deferred()
        self._hostname = hostname
        self._wql = wql
        self._data = ""

    def dataReceived(self, data):
        self._data += data

    def connectionLost(self, reason):
        from xml.etree import ElementTree
        tree = ElementTree.fromstring(self._data)
        print >>sys.stderr, self._hostname, "==>", self._wql
        print >>sys.stderr, tree.findtext("Envelope/Body/Fault/Reason/Text")
        print >>sys.stderr, tree.findtext(
            "Envelope/Body/Fault/Detail/MSFT_WmiError/Message")
        self.d.callback(None)


class WinrmClient(object):

    def __init__(self, agent, handler):
        self._agent = agent
        self._handler = handler

    @defer.inlineCallbacks
    def enumerate(self, hostname, username, password, wql):
        url = "http://{hostname}:5985/wsman".format(hostname=hostname)
        authstr = "{username}:{password}".format(username=username,
                                                 password=password)
        auth = 'Basic ' + base64.encodestring(authstr).strip()
        headers = Headers(
            {'Content-Type': ['application/soap+xml;charset=UTF-8'],
             'Authorization': [auth]})
        request_fmt_filename = get_request_template('enumerate')
        resource_uri_prefix = c.WMICIMV2
        cim_class = wql.split()[-1]
        resource_uri = resource_uri_prefix + '/' + cim_class
        enumeration_context = None
        try:
            while True:
                with open(request_fmt_filename) as f:
                    request_fmt = f.read()
                request = request_fmt.format(
                    resource_uri=resource_uri_prefix + '/*',
                    wql=wql,
                    enumeration_context=enumeration_context)
                if c.DEBUG:
                    print request
                body = StringProducer(request)
                response = yield self._agent.request('POST', url, headers,
                                                     body)
                print hostname, "HTTP status:", response.code
                if response.code != 200:
                    reader = ErrorReader(hostname, wql)
                    response.deliverBody(reader)
                    yield reader.d
                    raise Exception("HTTP status" + str(response.code))
                printer = ElementPrinter()
                handler = yield self._handler.handle_response(
                    response, resource_uri, cim_class, printer)
                print '\n', hostname, "==>", wql
                printer.print_elems_with_text()
                if not handler.enumeration_context:
                    break
                request_fmt_filename = get_request_template('pull')
                enumeration_context = handler.enumeration_context
        except Exception, e:
            print e
            raise


def send_requests(client, config):
    ds = []
    for hostname, (username, password) in config.hosts.iteritems():
        for wql in config.wqls:
            d = client.enumerate(hostname, username, password, wql)
            ds.append(d)
    dl = defer.DeferredList(ds)

    def dl_callback(results):
        failure_count = 0
        for success, result in results:
            if not success:
                failure_count += 1
        reactor.stop()
        if failure_count:
            print >>sys.stderr, 'There were', failure_count, "failures"
            sys.exit(1)
        print >>sys.stderr, "Processed", GLOBAL_ELEMENT_COUNT, "elements"

    dl.addCallback(dl_callback)


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("parser", choices=['cetree', 'etree', 'sax'])
    parser.add_argument("--debug", "-d", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    c.DEBUG = args.debug
    pool = HTTPConnectionPool(reactor, persistent=True)
    pool.maxPersistentPerHost = c.MAX_PERSISTENT_PER_HOST
    pool.cachedConnectionTimeout = c.CACHED_CONNECTION_TIMEOUT
    agent = Agent(reactor, pool=pool)
    if args.parser == 'etree':
        handler = r.ElementTreeResponseHandler()
    elif args.parser == 'cetree':
        handler = r.cElementTreeResponseHandler()
    elif args.parser == 'sax':
        handler = r.ExpatResponseHandler()
    else:
        raise Exception("unkown parser: " + args.parser)
    client = WinrmClient(agent, handler)
    from . import config
    reactor.callWhenRunning(send_requests, client, config)
    reactor.run()


if __name__ == '__main__':
    main()
