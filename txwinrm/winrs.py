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
from pprint import pprint
from argparse import ArgumentParser
from twisted.internet import reactor, defer, task
from .shell import RemoteShell, WinrsClient

logging.basicConfig()
log = logging.getLogger('zen.winrm')


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--config", "-c")
    parser.add_argument("--remote", "-r")
    parser.add_argument("--username", "-u")
    parser.add_argument("--password", "-p")
    parser.add_argument("--command", "-x")
    return parser.parse_args()


def print_output(stdout, stderr):
    for line in stdout:
        print ' ', line
    for line in stderr:
        print >>sys.stderr, ' ', line


@defer.inlineCallbacks
def get_output(shell, remote):
    stdout, stderr = yield task.deferLater(
        reactor, 2, shell.get_output)
    print 'Received from {0}:'.format(remote)
    print_output(stdout, stderr)


@defer.inlineCallbacks
def tx_main(args):
    remote = args.remote
    command = args.command
    try:
        shell = RemoteShell(remote, args.username, args.password)
        print 'Connecting to {0}.\n'.format(remote)
        yield shell.create()
        yield get_output(shell, remote)

        for i in range(10):
            print '\n', 'Sending to {0}:\n  {1}\n'.format(remote, command)
            yield shell.run_command(command)
            yield get_output(shell, remote)

        response = yield shell.delete()
        print_output(response.stdout, response.stderr)
        print "\nExit code from {0}: {1}".format(
            remote, response.exit_code)
    finally:
        if reactor.running:
            reactor.stop()


@defer.inlineCallbacks
def tx_main2(args):
    try:
        client = WinrsClient(args.remote, args.username, args.password)
        results = yield client.run_command(args.command)
        pprint(results)
    finally:
        reactor.stop()


def main():
    args = parse_args()
    if args.debug:
        log.setLevel(level=logging.DEBUG)
        defer.setDebugging(True)
    reactor.callWhenRunning(tx_main, args)
    reactor.run()

if __name__ == '__main__':
    main()
