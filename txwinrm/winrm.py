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

import logging
import sys
from argparse import ArgumentParser
from ConfigParser import RawConfigParser
from twisted.internet import reactor, defer
from twisted.internet.error import TimeoutError
from .enumerate import create_winrm_client
from .util import UnauthorizedError

logging.basicConfig()
log = logging.getLogger('zen.winrm')
GLOBAL_ELEMENT_COUNT = 0
exit_status = 0


def get_vmpeak():
    with open('/proc/self/status') as status:
        for line in status:
            key, value = line.split(None, 1)
            if key == 'VmPeak:':
                return value


def print_items(items, hostname, wql, include_header):
    global GLOBAL_ELEMENT_COUNT
    if include_header:
        print '\n', hostname, "==>", wql
        indent = '  '
    else:
        indent = ''
    is_first_item = True
    for item in items:
        if is_first_item:
            is_first_item = False
        else:
            print '{0}{1}'.format(indent, '-' * 4)
        for name, value in vars(item).iteritems():
            GLOBAL_ELEMENT_COUNT += 1
            text = value
            if isinstance(value, list):
                text = ', '.join(value)
            print '{0}{1} = {2}'.format(indent, name, text)


@defer.inlineCallbacks
def get_remote_process_stats(client):
    wql = 'select Name, IDProcess, PercentProcessorTime,' \
          'Timestamp_Sys100NS from Win32_PerfRawData_PerfProc_Process ' \
          'where name like "wmi%"'
    items = yield client.enumerate(wql)
    defer.returnValue(items)


def calculate_remote_cpu_util(initial_stats, final_stats):
    for hostname, initial_stats_items in initial_stats.iteritems():
        final_stats_items = final_stats[hostname]
        print >>sys.stderr, "   ", hostname
        for initial_stats_item in initial_stats_items:
            name = initial_stats_item.Name
            pid = initial_stats_item.IDProcess
            for final_stats_item in final_stats_items:
                if pid == final_stats_item.IDProcess:
                    break
            else:
                print >>sys.stderr, "WARNING: Could not find final process " \
                                    "stats for", hostname, pid
                continue
            x1 = float(final_stats_item.PercentProcessorTime)
            x0 = float(initial_stats_item.PercentProcessorTime)
            y1 = float(final_stats_item.Timestamp_Sys100NS)
            y0 = float(initial_stats_item.Timestamp_Sys100NS)
            cpu_pct = (x1 - x0) / (y1 - y0)
            fmt = "      {cpu_pct:.2%} of CPU time used by {name} "\
                  "process with pid {pid}"
            print >>sys.stderr, fmt.format(hostname=hostname, cpu_pct=cpu_pct,
                                           name=name, pid=pid)


@defer.inlineCallbacks
def get_initial_wmiprvse_stats(config):
    initial_wmiprvse_stats = {}
    good_hosts = []
    for hostname, (username, password) in config.hosts.iteritems():
        try:
            client = create_winrm_client(hostname, username, password)
            initial_wmiprvse_stats[hostname] = \
                yield get_remote_process_stats(client)
            good_hosts.append((hostname, username, password))
        except UnauthorizedError:
            continue
        except TimeoutError:
            continue
    defer.returnValue((initial_wmiprvse_stats, good_hosts))


@defer.inlineCallbacks
def print_summary(results, config, initial_wmiprvse_stats, good_hosts):
    global exit_status
    final_wmiprvse_stats = {}
    for hostname, username, password in good_hosts:
        client = create_winrm_client(hostname, username, password)
        final_wmiprvse_stats[hostname] = \
            yield get_remote_process_stats(client)
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
    print >>sys.stderr, '  Failed to process', failure_count,\
        "responses"
    print >>sys.stderr, "  Peak virtual memory useage:", get_vmpeak()
    print >>sys.stderr, '  Remote CPU utilization:'
    calculate_remote_cpu_util(initial_wmiprvse_stats,
                              final_wmiprvse_stats)


@defer.inlineCallbacks
def send_requests(config, do_summary):
    global exit_status
    if do_summary:
        initial_wmiprvse_stats, good_hosts = \
            yield get_initial_wmiprvse_stats(config)
    else:
        initial_wmiprvse_stats = None
        hostname, (username, password) = config.hosts.items()[0]
        good_hosts = [(hostname, username, password)]
    if not good_hosts:
        exit_status = 1
        reactor.stop()
        return
    ds = []
    for hostname, username, password in good_hosts:
        client = create_winrm_client(hostname, username, password)
        for wql in config.wqls:
            d = client.enumerate(wql)
            d.addCallback(print_items, hostname, wql, do_summary)
            ds.append(d)
    dl = defer.DeferredList(ds, consumeErrors=True)

    @defer.inlineCallbacks
    def dl_callback(results):
        if do_summary:
            yield print_summary(
                results, config, initial_wmiprvse_stats, good_hosts)

    def stop_reactor(results):
        reactor.stop()

    dl.addCallback(dl_callback)
    dl.addBoth(stop_reactor)


class Config(object):
    pass


def parse_config_file(filename):
    parser = RawConfigParser(allow_no_value=True)
    parser.read(filename)
    creds = {}
    index = dict(hostname=0, password=1)
    for key, value in parser.items('credentials'):
        k1, k2 = key.split('.')
        if k1 not in creds:
            creds[k1] = [None, None]
        creds[k1][index[k2]] = value
    config = Config()
    config.hosts = {}
    for hostname, cred_key in parser.items('targets'):
        config.hosts[hostname] = (creds[cred_key])
    config.wqls = parser.options('wqls')
    return config


def adapt_args_to_config(args):
    config = Config()
    config.hosts = {args.remote: (args.username, args.password)}
    config.wqls = [args.filter]
    return config


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--config", "-c")
    parser.add_argument("--remote", "-r")
    parser.add_argument("--username", "-u")
    parser.add_argument("--password", "-p")
    parser.add_argument("--filter", "-f")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.debug:
        log.setLevel(level=logging.DEBUG)
        defer.setDebugging(True)
    if args.config:
        config = parse_config_file(args.config)
        do_summary = True
    elif args.remote and args.username and args.password and args.filter:
        config = adapt_args_to_config(args)
        do_summary = False
    else:
        print >>sys.stderr, "ERROR: You must specify a config file with -c " \
                            "or specify remote, username, password and filter"
        sys.exit(1)
    reactor.callWhenRunning(send_requests, config, do_summary)
    reactor.run()
    sys.exit(exit_status)

if __name__ == '__main__':
    main()
