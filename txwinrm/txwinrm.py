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
import httplib
from argparse import ArgumentParser

from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol
from twisted.internet.error import TimeoutError
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers

from . import contstants as c
from . import response as r

GLOBAL_ELEMENT_COUNT = 0
CONNECT_TIMEOUT = 5


def get_vmpeak():
    with open('/proc/self/status') as status:
        for line in status:
            key, value = line.split(None, 1)
            if key == 'VmPeak:':
                return value


def get_request_template(name):
    basedir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(basedir, 'request', name + '.xml')


class EnumerationContextTracker(object):

    def __init__(self):
        self._enumeration_context = None
        self._end_of_sequence = False

    @property
    def enumeration_context(self):
        if not self._end_of_sequence:
            return self._enumeration_context

    def append_element(self, uri, localname, text):
        if uri == c.XML_NS_ENUMERATION:
            if localname == c.WSENUM_ENUMERATION_CONTEXT:
                self._enumeration_context = text
            elif localname == c.WSENUM_END_OF_SEQUENCE:
                self._end_of_sequence = True


class ElementPrinter(EnumerationContextTracker):

    def __init__(self):
        EnumerationContextTracker.__init__(self)
        self._elems_with_text = []
        self._longest_tag = 0

    def new_instance(self):
        demarc = '-' * self._longest_tag
        self._elems_with_text.append((demarc, demarc))

    def append_element(self, uri, localname, text):
        EnumerationContextTracker.append_element(self, uri, localname, text)
        global GLOBAL_ELEMENT_COUNT
        GLOBAL_ELEMENT_COUNT += 1
        tag = uri.split('/')[-1] + '.' + localname
        self._elems_with_text.append((tag, text))
        if len(tag) > self._longest_tag:
            self._longest_tag = len(tag)

    def print_elements_with_text(self):
        for tag, text in self._elems_with_text:
            print '{0:>{width}} {1}'.format(tag, text, width=self._longest_tag)


class ProcessStatsAccumulator(EnumerationContextTracker):

    def __init__(self):
        EnumerationContextTracker.__init__(self)
        self.process_stats = []

    def new_instance(self):
        self.process_stats.append({})

    def append_element(self, uri, localname, text):
        EnumerationContextTracker.append_element(self, uri, localname, text)
        print "DEBUG2", uri, localname, text
        if not uri and localname in ['IDProcess', 'PercentProcessorTime',
                                     'Timestamp_Sys100NS']:
            self.process_stats[-1][localname] = text


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
        self._unauthorized_hosts = []
        self._timedout_hosts = []

    @defer.inlineCallbacks
    def enumerate(self, hostname, username, password, wql, accumulator):
        if hostname in self._unauthorized_hosts:
            if c.DEBUG:
                print hostname, "previously returned unauthorized. Skipping."
            return
        if hostname in self._timedout_hosts:
            if c.DEBUG:
                print hostname, "previously timed out. Skipping."
            return
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
                if c.DEBUG:
                    print hostname, "HTTP status:", response.code
                if response.code == httplib.UNAUTHORIZED:
                    if hostname in self._unauthorized_hosts:
                        return
                    self._unauthorized_hosts.append(hostname)
                    raise Exception("unauthorized, check username and "
                                    "password.")
                if response.code != 200:
                    reader = ErrorReader(hostname, wql)
                    response.deliverBody(reader)
                    yield reader.d
                    raise Exception("HTTP status" + str(response.code))
                yield self._handler.handle_response(response, resource_uri,
                                                    cim_class, accumulator)
                print '\n', hostname, "==>", wql
                if not accumulator.enumeration_context:
                    break
                request_fmt_filename = get_request_template('pull')
                enumeration_context = accumulator.enumeration_context
        except TimeoutError, e:
            if hostname in self._timedout_hosts:
                return
            self._timedout_hosts.append(hostname)
            print >>sys.stderr, "ERROR:", hostname, e
            raise
        except Exception, e:
            print >>sys.stderr, "ERROR:", hostname, e
            raise


@defer.inlineCallbacks
def get_remote_process_stats(client, hostname, username, password,
                             process_name):
    wql_fmt = 'select IDProcess, PercentProcessorTime, Timestamp_Sys100NS ' \
              'from Win32_PerfRawData_PerfProc_Process where name = ' \
              '"{process_name}"'
    wql = wql_fmt.format(process_name=process_name)
    accumulator = ProcessStatsAccumulator()
    yield client.enumerate(hostname, username, password, wql, accumulator)
    from pprint import pprint
    print "Process stats!!!!"
    pprint(accumulator.process_stats)
    defer.returnValue(accumulator.process_stats)


def calculate_remote_cpu_util(initial_stats, final_stats):
    for hostname, initial_stats_dicts in initial_stats.iteritems():
        final_stats_dicts = final_stats[hostname]
        for initial_stats_dict in initial_stats_dicts:
            pid = initial_stats_dict["IDProcess"]
            for final_stats_dict in final_stats_dicts:
                if pid == final_stats_dict["IDProcess"]:
                    break
            else:
                raise Exception("Could not find final process stats for "
                                + hostname + " " + pid)
            x1 = float(final_stats_dict['PercentProcessorTime'])
            x0 = float(initial_stats_dict['PercentProcessorTime'])
            y1 = float(final_stats_dict['Timestamp_Sys100NS'])
            y0 = float(initial_stats_dict['Timestamp_Sys100NS'])
            cpu_pct = (x1 - x0) / (y1 - y0)
            fmt = "{hostname} {cpu_pct:.2%} of CPU time used by wmiprvse "\
                  "process with pid {pid}"
            print >>sys.stderr, fmt.format(hostname=hostname, cpu_pct=cpu_pct,
                                           pid=pid)

exit_status = 0


@defer.inlineCallbacks
def send_requests(client, config):
    printers = []
    initial_wmiprvse_stats = {}
    ds = []
    for hostname, (username, password) in config.hosts.iteritems():
        initial_wmiprvse_stats[hostname] = yield get_remote_process_stats(
            client, hostname, username, password, "wmiprvse")
        print "DEBUG3", initial_wmiprvse_stats
        for wql in config.wqls:
            printer = ElementPrinter()
            printers.append(printer)
            d = client.enumerate(hostname, username, password, wql, printer)
            ds.append(d)
    print len(ds), "in DeferredList"
    dl = defer.DeferredList(ds, consumeErrors=True)

    @defer.inlineCallbacks
    def dl_callback(results):
        print "dl_callback"
        global exit_status
        for printer in printers:
            printer.print_elements_with_text()
        final_wmiprvse_stats = {}
        for hostname, (username, password) in config.hosts.iteritems():
            final_wmiprvse_stats[hostname] = yield get_remote_process_stats(
                client, hostname, username, password, "wmiprvse")
        calculate_remote_cpu_util(initial_wmiprvse_stats, final_wmiprvse_stats)
        failure_count = 0
        for success, result in results:
            if not success:
                failure_count += 1
        if failure_count:
            print >>sys.stderr, 'There were', failure_count, "failures"
            exit_status = 1
        else:
            print >>sys.stderr, "Processed", GLOBAL_ELEMENT_COUNT, "elements"
        reactor.stop()

    dl.addCallback(dl_callback)


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--parser", "-p", default='sax',
                        choices=['cetree', 'etree', 'sax'])
    parser.add_argument("--debug", "-d", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    c.DEBUG = args.debug
    pool = HTTPConnectionPool(reactor, persistent=True)
    pool.maxPersistentPerHost = c.MAX_PERSISTENT_PER_HOST
    pool.cachedConnectionTimeout = c.CACHED_CONNECTION_TIMEOUT
    agent = Agent(reactor, connectTimeout=CONNECT_TIMEOUT, pool=pool)
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
    print >>sys.stderr, "Peak virtual memory useage:", get_vmpeak()
    sys.exit(exit_status)


if __name__ == '__main__':
    main()
