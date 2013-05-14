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
from datetime import datetime
from twisted.internet import reactor, defer, task
from . import app
from .shell import create_typeperf

log = logging.getLogger('zen.winrm')


class TypeperfUtility(app.BaseUtility):

    @defer.inlineCallbacks
    def tx_main(self, args, config):
        try:
            typeperf = create_typeperf(
                args.remote, args.authentication, args.username, args.password,
                args.scheme, args.port)
            yield typeperf.start(args.counters, args.si)
            i = 0
            while args.sc == 0 or i < args.sc:
                if args.sc > 0:
                    i += 1
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

    def add_args(self, parser):
        parser.add_argument("--si", type=int, default=1,
                            help="time between samples in seconds")
        parser.add_argument("--sc", type=int, default=0,
                            help="number of samples to collect")
        parser.add_argument("counters", nargs='+',
                            help="performance counter paths to log")

    def check_args(self, args):
        if args.config:
            print >>sys.stderr, \
                "ERROR: The typeperf command does not support a " \
                "configuration file at this time."
        return not args.config

if __name__ == '__main__':
    app.main(TypeperfUtility())
