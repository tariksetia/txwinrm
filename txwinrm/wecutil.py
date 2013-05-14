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


def pprint_event(event):
    pprint(event)


class WecUtility(app.BaseUtility):

    @defer.inlineCallbacks
    def tx_main(self, args, config):
        try:
            subscription = create_event_subscription(
                args.remote, args.authentication, args.username, args.password,
                args.scheme, args.port)
            yield subscription.subscribe(path=args.path, select=args.select)
            i = 0
            while args.num_pulls == 0 or i < args.num_pulls:
                i += 1
                sys.stdout.write('Pull #{0}'.format(i))
                if args.num_pulls > 0:
                    sys.stdout.write(' of {0}'.format(args.num_pulls))
                print
                yield task.deferLater(
                    reactor, 1, subscription.pull, pprint_event)
            yield subscription.unsubscribe()
        finally:
            if reactor.running:
                reactor.stop()

    def add_args(self, parser):
        parser.add_argument("--path", "-p", default='Application')
        parser.add_argument("--select", "-s", default='*')
        parser.add_argument("--num-pulls", "-n", type=int, default=0)

    def check_args(self, args):
        if args.config:
            print >>sys.stderr, \
                "ERROR: The wecutil command does not support a " \
                "configuration file at this time."
        return not args.config

if __name__ == '__main__':
    app.main(WecUtility())
