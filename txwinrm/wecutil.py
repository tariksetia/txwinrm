##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

import sys
import logging
from twisted.internet import defer, task, reactor
from . import app
from .subscribe import create_event_subscription

log = logging.getLogger('zen.winrm')


class SubscriptionInfo(object):

    def __init__(self, path=None, select=None):
        self.path = path
        self.select = select

    def __repr__(self):
        return "{0} {1}".format(self.path, self.select)


class WecutilStrategy(object):

    def __init__(self):
        self._event_count = 0
        self._d = defer.Deferred()
        self._active_count = 0

    @property
    def count_summary(self):
        return '{0} events'.format(self._event_count)

    @defer.inlineCallbacks
    def _do_pull(
            self, i, num_pulls, hostname, subscr_info, subscription):

        if num_pulls > 0 and i == num_pulls:
            yield subscription.unsubscribe()
            self._active_count -= 1
            if self._active_count == 0:
                self._d.callback(None)
            return

        i += 1
        sys.stdout.write('Pull #{0}'.format(i))
        if num_pulls > 0:
            sys.stdout.write(' of {0}'.format(num_pulls))
        print

        def print_event(event):
            print "{0} {1} {2}".format(hostname, subscr_info, event)

        yield subscription.pull(print_event)
        task.deferLater(reactor, 0, self._do_pull, i, num_pulls, hostname,
                        subscr_info, subscription)

    @defer.inlineCallbacks
    def act(self, good_conn_infos, args, config):
        for conn_info in good_conn_infos:
            for subscr_info in config.subscr_infos:
                subscription = create_event_subscription(conn_info)
                yield subscription.subscribe(
                    subscr_info.path, subscr_info.select)
                self._active_count += 1
                self._do_pull(conn_info.hostname, subscr_info, subscription)
        yield self._d


class WecUtility(app.ConfigDrivenUtility):

    def add_args(self, parser):
        parser.add_argument("--path", "-p", default='Application')
        parser.add_argument("--select", "-s", default='*')
        parser.add_argument("--num-pulls", "-n", type=int, default=0)

    def check_args(self, args):
        return True

    def add_config(self, parser, config):
        dct = {}
        for key, value in parser.items('subscriptions'):
            k1, k2 = key.split('.')
            if k2 not in ['path', 'select']:
                log.error("Illegal subscription key: {0}".format(key))
                continue
            if k1 not in dct:
                dct[k1] = SubscriptionInfo()
            setattr(dct[k1], k2)
        config.subscr_infos = dct.values()

    def adapt_args_to_config(self, args, config):
        config.subscr_infos = [SubscriptionInfo(args.path, args.select)]

if __name__ == '__main__':
    app.main(WecUtility(WecutilStrategy()))
