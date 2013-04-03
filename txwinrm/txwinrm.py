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
from twisted.web.client import Agent
from twisted.web.http_headers import Headers

from . import contstants as c
from . import response as r

GLOBAL_ELEMENT_COUNT = 0
CONNECT_TIMEOUT = 1


def get_vmpeak():
    with open('/proc/self/status') as status:
        for line in status:
            key, value = line.split(None, 1)
            if key == 'VmPeak:':
                return value


def get_request_template(name):
    basedir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(basedir, 'request', name + '.xml')


class ElementPrinter(object):

    def __init__(self, hostname, wql):
        self._hostname = hostname
        self._wql = wql
        self._elems_with_text = []
        self._demarc = '-' * 4

    def new_instance(self):
        if self._elems_with_text:
            self._elems_with_text.append((self._demarc, ''))

    def append_element(self, uri, localname, text):
        global GLOBAL_ELEMENT_COUNT
        if text:
            GLOBAL_ELEMENT_COUNT += 1
        self._elems_with_text.append((localname, text))

    def print_elements_with_text(self, result):
        print '\n', self._hostname, "==>", self._wql
        for tag, text in self._elems_with_text:
            if tag == self._demarc:
                print ' ', self._demarc
            else:
                print '  {0} = {1}'.format(tag, text)


class ProcessStatsAccumulator(object):

    def __init__(self):
        self.process_stats = []

    def new_instance(self):
        self.process_stats.append({})

    def append_element(self, uri, localname, text):
        if not uri and localname in ['Name', 'IDProcess',
                                     'PercentProcessorTime',
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
        print >>sys.stderr, self._hostname, "-->", self._wql
        print >>sys.stderr, tree.findtext("Envelope/Body/Fault/Reason/Text")
        print >>sys.stderr, tree.findtext(
            "Envelope/Body/Fault/Detail/MSFT_WmiError/Message")
        self.d.callback(None)


class Unauthorized(Exception):
    pass


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
                    raise Unauthorized("unauthorized, check username and "
                                       "password.")
                if response.code != 200:
                    reader = ErrorReader(hostname, wql)
                    response.deliverBody(reader)
                    yield reader.d
                    raise Exception("HTTP status" + str(response.code))
                enumeration_context = yield self._handler.handle_response(
                    response, resource_uri, cim_class, accumulator)
                if not enumeration_context:
                    break
                request_fmt_filename = get_request_template('pull')
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
def get_remote_process_stats(client, hostname, username, password):
    wql = 'select Name, IDProcess, PercentProcessorTime,' \
          'Timestamp_Sys100NS from Win32_PerfRawData_PerfProc_Process ' \
          'where name like "wmi%"'
    accumulator = ProcessStatsAccumulator()
    yield client.enumerate(hostname, username, password, wql, accumulator)
    defer.returnValue(accumulator.process_stats)


def calculate_remote_cpu_util(initial_stats, final_stats):
    for hostname, initial_stats_dicts in initial_stats.iteritems():
        final_stats_dicts = final_stats[hostname]
        print >>sys.stderr, "   ", hostname
        for initial_stats_dict in initial_stats_dicts:
            name = initial_stats_dict["Name"]
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
            fmt = "      {cpu_pct:.2%} of CPU time used by {name} "\
                  "process with pid {pid}"
            print >>sys.stderr, fmt.format(hostname=hostname, cpu_pct=cpu_pct,
                                           name=name, pid=pid)


exit_status = 0


@defer.inlineCallbacks
def send_requests(client, config):
    global exit_status
    initial_wmiprvse_stats = {}
    good_hosts = []
    for hostname, (username, password) in config.hosts.iteritems():
        try:
            initial_wmiprvse_stats[hostname] = yield get_remote_process_stats(
                client, hostname, username, password)
            good_hosts.append((hostname, username, password))
        except Unauthorized:
            continue
        except TimeoutError:
            continue
    if not good_hosts:
        exit_status = 1
        reactor.stop()
        return
    ds = []
    for hostname, username, password in good_hosts:
        for wql in config.wqls:
            printer = ElementPrinter(hostname, wql)
            d = client.enumerate(hostname, username, password, wql, printer)
            d.addCallback(printer.print_elements_with_text)
            ds.append(d)
    dl = defer.DeferredList(ds, consumeErrors=True)

    @defer.inlineCallbacks
    def dl_callback(results):
        global exit_status
        final_wmiprvse_stats = {}
        for hostname, (username, password) in config.hosts.iteritems():
            final_wmiprvse_stats[hostname] = yield get_remote_process_stats(
                client, hostname, username, password)
        print >>sys.stderr, '\nSummary:'
        print >>sys.stderr, '  Connected to', len(good_hosts), 'of', \
                            len(config.hosts), 'hosts'
        print >>sys.stderr, "  Processed", GLOBAL_ELEMENT_COUNT, "elements"
        failure_count = 0
        for success, result in results:
            if not success:
                failure_count += 1
        if failure_count:
            exit_status = 1
        print >>sys.stderr, '  Failed to process', failure_count, "responses"
        print >>sys.stderr, "  Peak virtual memory useage:", get_vmpeak()
        print >>sys.stderr, '  Remote CPU utilization:'
        calculate_remote_cpu_util(initial_wmiprvse_stats, final_wmiprvse_stats)
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
    try:
        # HTTPConnectionPool has been present since Twisted version 12.1
        from twisted.web.client import HTTPConnectionPool
        pool = HTTPConnectionPool(reactor, persistent=True)
        pool.maxPersistentPerHost = c.MAX_PERSISTENT_PER_HOST
        pool.cachedConnectionTimeout = c.CACHED_CONNECTION_TIMEOUT
        agent = Agent(reactor, connectTimeout=CONNECT_TIMEOUT, pool=pool)
    except ImportError:
        agent = Agent(reactor, connectTimeout=CONNECT_TIMEOUT)
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
    sys.exit(exit_status)


if __name__ == '__main__':
    main()
