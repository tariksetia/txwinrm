##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import sys
import logging
from argparse import ArgumentParser
from datetime import datetime
from twisted.internet import reactor, defer, task
from .shell import create_typeperf

logging.basicConfig()
log = logging.getLogger('zen.winrm')


@defer.inlineCallbacks
def tx_main(args):
    try:
        typeperf = create_typeperf(args.remote, args.username, args.password)
        yield typeperf.start(args.counters, args.si)
        for i in xrange(args.sc):
            results, stderr = yield task.deferLater(
                reactor, args.si, typeperf.receive)
            for key, values in results.iteritems():
                print key
                for timestamp, value in values:
                    date_str = datetime.strftime(timestamp, "%H:%M:%S")
                    print '  {0}: {1}'.format(date_str, value)
            for line in stderr:
                print >>sys.stderr, line
        yield typeperf.stop()
    finally:
        reactor.stop()


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--config", "-c")
    parser.add_argument("--remote", "-r")
    parser.add_argument("--username", "-u")
    parser.add_argument("--password", "-p")
    parser.add_argument("--si", type=int, default=1)
    parser.add_argument("--sc", type=int, default=5)
    parser.add_argument("counters", nargs='+')
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
