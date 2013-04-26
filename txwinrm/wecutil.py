##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
from pprint import pprint
from argparse import ArgumentParser
from twisted.internet import reactor, defer, task
from .subscribe import create_event_subscription

logging.basicConfig()
log = logging.getLogger('zen.winrm')


def pprint_event(event):
    pprint(event)


@defer.inlineCallbacks
def tx_main(args):
    try:
        subscription = create_event_subscription(
            args.remote, args.username, args.password)
        subscription.subscribe(path='Application', select='*')
        for i in xrange(10):
            yield task.deferLater(reactor, 1, subscription.pull, pprint_event)
        subscription.unsubscribe()
    finally:
        reactor.stop()


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--config", "-c")
    parser.add_argument("--remote", "-r")
    parser.add_argument("--username", "-u")
    parser.add_argument("--password", "-p")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.debug:
        log.setLevel(level=logging.DEBUG)
        defer.setDebugging(True)
    reactor.callWhenRunning(tx_main, args)
    reactor.run()

if __name__ == '__main__':
    main()
