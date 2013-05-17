##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

"""
Use twisted web client to enumerate/pull WQL query.
"""

import sys
from twisted.internet import defer
from twisted.internet.error import TimeoutError
from . import app
from .enumerate import create_winrm_client
from .util import UnauthorizedError

GLOBAL_ELEMENT_COUNT = 0


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
    cpu_util_info = []
    for hostname, initial_stats_items in initial_stats.iteritems():
        final_stats_items = final_stats[hostname]
        host_cpu_util_info = []
        cpu_util_info.append([hostname, host_cpu_util_info])
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
            host_cpu_util_info.append((cpu_pct, name, pid))
    return cpu_util_info


def print_remote_cpu_util(cpu_util_info):
    for hostname, stats in cpu_util_info:
        print >>sys.stderr, "   ", hostname
        for cpu_pct, name, pid in stats:
            fmt = "      {cpu_pct:.2%} of CPU time used by {name} "\
                  "process with pid {pid}"
            print >>sys.stderr, fmt.format(hostname=hostname, cpu_pct=cpu_pct,
                                           name=name, pid=pid)


@defer.inlineCallbacks
def get_initial_wmiprvse_stats(config):
    initial_wmiprvse_stats = {}
    good_hosts = []
    for hostname, (auth_type, username, password, scheme, port) \
            in config.hosts.iteritems():
        try:
            client = create_winrm_client(
                hostname, auth_type, username, password, scheme, port)
            initial_wmiprvse_stats[hostname] = \
                yield get_remote_process_stats(client)
            good_hosts.append((
                hostname, auth_type, username, password, scheme, port))
        except UnauthorizedError:
            continue
        except TimeoutError:
            continue
    defer.returnValue((initial_wmiprvse_stats, good_hosts))


@defer.inlineCallbacks
def print_summary(results, config, initial_wmiprvse_stats, good_hosts):
    global exit_status
    final_wmiprvse_stats = {}
    for hostname, auth_type, username, password, scheme, port in good_hosts:
        client = create_winrm_client(
            hostname, auth_type, username, password, scheme, port)
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
    cpu_util_info = calculate_remote_cpu_util(
        initial_wmiprvse_stats, final_wmiprvse_stats)
    print_remote_cpu_util(cpu_util_info)


class WinrmUtility(app.BaseUtility):

    @defer.inlineCallbacks
    def tx_main(self, unused_args, config):
        do_summary = len(config.hosts) > 1
        if do_summary:
            initial_wmiprvse_stats, good_hosts = \
                yield get_initial_wmiprvse_stats(config)
        else:
            initial_wmiprvse_stats = None
            hostname, (auth_type, username, password, scheme, port) = \
                config.hosts.items()[0]
            good_hosts = [(
                hostname, auth_type, username, password, scheme, port)]
        if not good_hosts:
            app.exit_status = 1
            app.stop_reactor()
            return
        ds = []
        for hostname, auth_type, username, password, scheme, port \
                in good_hosts:
            client = create_winrm_client(
                hostname, auth_type, username, password, scheme, port)
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

        dl.addCallback(dl_callback)
        dl.addBoth(app.stop_reactor)

    def add_args(self, parser):
        parser.add_argument("--filter", "-f")

    def check_args(self, args):
        legit = args.config or args.filter
        if not legit:
            print >>sys.stderr, "ERROR: You must specify a config file with " \
                                "-c or specify a WQL filter with -f"
        return legit

    def add_config(self, parser, config):
        config.wqls = parser.options('wqls')

    def adapt_args_to_config(self, args, config):
        config.wqls = [args.filter]

if __name__ == '__main__':
    app.main(WinrmUtility())
