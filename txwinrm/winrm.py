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
from . import app
from .enumerate import create_winrm_client


GLOBAL_ELEMENT_COUNT = 0


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


class WinrmUtility(object):

    @defer.inlineCallbacks
    def tx_main(self, unused_args, config):
        do_summary = len(config.conn_infos) > 1
        if do_summary:
            initial_wmiprvse_stats, good_conn_infos = \
                yield get_initial_wmiprvse_stats(config)
        else:
            initial_wmiprvse_stats = None
            good_conn_infos = [config.conn_infos[0]]
        if not good_conn_infos:
            app.exit_status = 1
            app.stop_reactor()
            return
        ds = []
        for conn_info in good_conn_infos:
            client = create_winrm_client(conn_info)
            for wql in config.wqls:
                d = client.enumerate(wql)
                d.addCallback(print_items, conn_info.hostname, wql, do_summary)
                ds.append(d)
        dl = defer.DeferredList(ds, consumeErrors=True)

        @defer.inlineCallbacks
        def dl_callback(results):
            if do_summary:
                yield print_summary(
                    results, config, initial_wmiprvse_stats, good_conn_infos)

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
