##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import sys
import cmd
import logging
from pprint import pprint
from argparse import ArgumentParser
from twisted.internet import reactor, defer, threads
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


class WinrsCmd(cmd.Cmd):

    def __init__(self, shell):
        cmd.Cmd.__init__(self)
        self._shell = shell
        self.prompt = shell.prompt

    def default(self, line):
        response = threads.blockingCallFromThread(
            reactor, self._run_command, line)
        print '\n'.join(response.stdout)
        print >>sys.stderr, '\n'.join(response.stderr)

    @defer.inlineCallbacks
    def _run_command(self, line):
        response = yield self._shell.run_command(line)
        defer.returnValue(response)

    def do_exit(self, line):
        reactor.callFromThread(self._exit)
        return True

    @defer.inlineCallbacks
    def _exit(self):
        yield self._shell.delete()
        reactor.stop()

    def postloop(self):
        print


@defer.inlineCallbacks
def tx_main(args):
    remote = args.remote
    shell = RemoteShell(remote, args.username, args.password)
    response = yield shell.create()
    intro = '\n'.join(response.stdout)
    winrs_cmd = WinrsCmd(shell)
    reactor.callInThread(winrs_cmd.cmdloop, intro)


@defer.inlineCallbacks
def tx_main2(args):
    remote = args.remote
    command = args.command
    try:
        shell = RemoteShell(remote, args.username, args.password)
        print 'Creating shell on {0}.'.format(remote)
        yield shell.create()
        for i in range(2):
            print '\nSending to {0}:\n  {1}'.format(remote, command)
            response = yield shell.run_command(command)
            print '\nReceived from {0}:'.format(remote)
            print_output(response.stdout, response.stderr)
        response = yield shell.delete()
        print "\nDeleted shell on {0}.".format(remote)
        print_output(response.stdout, response.stderr)
        print "\nExit code of shell on {0}: {1}".format(
            remote, response.exit_code)
    finally:
        if reactor.running:
            reactor.stop()


@defer.inlineCallbacks
def tx_main3(args):
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
