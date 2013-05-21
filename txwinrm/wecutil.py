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
from pprint import pprint
from twisted.internet import reactor, defer, task
from . import app
from .subscribe import create_event_subscription

log = logging.getLogger('zen.winrm')


class SubscriptionInfo(object):

    def __init__(self, path=None, select=None):
        self.path = path
        self.select = select


def pprint_event(event):
    pprint(event)


@defer.inlineCallbacks
def do_subscription(conn_info, subscr_info, num_pulls):
    subscription = create_event_subscription(conn_info)
    yield subscription.subscribe(
        path=subscr_info.path, select=subscr_info.select)
    i = 0
    while num_pulls == 0 or i < num_pulls:
        i += 1
        sys.stdout.write('Pull #{0}'.format(i))
        if num_pulls > 0:
            sys.stdout.write(' of {0}'.format(num_pulls))
        print
        yield task.deferLater(
            reactor, 1, subscription.pull, pprint_event)
    yield subscription.unsubscribe()


class WecUtility(app.BaseUtility):

    @defer.inlineCallbacks
    def tx_main(self, args, config):
        try:
            for conn_info in config.conn_infos:
                for subscr_info in config.subscr_infos:
                    try:
                        do_subscription(conn_info, subscr_info)
                    except Exception as e:
                        log.error('Could not subscribe. {0} {1}'.format(
                            conn_info.hostname, e))
                        continue
        finally:
            if reactor.running:
                reactor.stop()

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
    app.main(WecUtility())
