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
from twisted.internet import reactor, defer, task, threads
from .shell import RemoteShell, LongRunningCommand, WinrsClient

logging.basicConfig()
log = logging.getLogger('zen.winrm')


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
def long_running_main(args):
    try:
        client = LongRunningCommand(args.remote, args.username, args.password)
        yield client.run_command(args.command)
        for i in xrange(5):
            stdout, stderr = yield task.deferLater(
                reactor, 1, client.get_output)
            print_output(stdout, stderr)
        yield client.exit()
    finally:
        reactor.stop()


@defer.inlineCallbacks
def interactive_main(args):
    remote = args.remote
    shell = RemoteShell(remote, args.username, args.password)
    response = yield shell.create()
    intro = '\n'.join(response.stdout)
    winrs_cmd = WinrsCmd(shell)
    reactor.callInThread(winrs_cmd.cmdloop, intro)


@defer.inlineCallbacks
def batch_main(args):
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
def single_shot_main(args):
    try:
        client = WinrsClient(args.remote, args.username, args.password)
        results = yield client.run_command(args.command)
        pprint(results)
    finally:
        reactor.stop()


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--interactive", "-i", action="store_true")
    parser.add_argument("--single-shot", "-s", action="store_true")
    parser.add_argument("--batch", "-b", action="store_true")
    parser.add_argument("--long-running", "-l", action="store_true")
    parser.add_argument("--config", "-c")
    parser.add_argument("--remote", "-r")
    parser.add_argument("--username", "-u")
    parser.add_argument("--password", "-p")
    parser.add_argument("--command", "-x")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.debug:
        log.setLevel(level=logging.DEBUG)
        defer.setDebugging(True)
    if args.interactive:
        tx_main = interactive_main
    elif args.single_shot:
        tx_main = single_shot_main
    elif args.batch:
        tx_main = batch_main
    else:
        tx_main = long_running_main
    reactor.callWhenRunning(tx_main, args)
    reactor.run()

if __name__ == '__main__':
    main()
