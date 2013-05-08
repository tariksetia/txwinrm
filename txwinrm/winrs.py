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
from pprint import pprint
from twisted.internet import reactor, defer, task, threads
from . import app
from .shell import create_long_running_command, create_single_shot_command, \
    create_remote_shell


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
        client = create_long_running_command(
            args.remote, args.authentication, args.username, args.password)
        yield client.start(args.command)
        for i in xrange(5):
            stdout, stderr = yield task.deferLater(
                reactor, 1, client.receive)
            print_output(stdout, stderr)
        yield client.stop()
    finally:
        reactor.stop()


@defer.inlineCallbacks
def interactive_main(args):
    remote = args.remote
    shell = create_remote_shell(
        remote, args.authentication, args.username, args.password)
    response = yield shell.create()
    intro = '\n'.join(response.stdout)
    winrs_cmd = WinrsCmd(shell)
    reactor.callInThread(winrs_cmd.cmdloop, intro)


@defer.inlineCallbacks
def batch_main(args):
    remote = args.remote
    command = args.command
    try:
        shell = create_remote_shell(
            remote, args.authentication, args.username, args.password)
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
        client = create_single_shot_command(
            args.remote, args.authentication, args.username, args.password)
        results = yield client.run_command(args.command)
        pprint(results)
    finally:
        reactor.stop()


def tx_main(args, config):
    if args.kind[0] == "long":
        long_running_main(args)
    elif args.kind[0] == "single":
        single_shot_main(args)
    elif args.kind[0] == "batch":
        batch_main(args)
    else:
        interactive_main(args)


def add_args(parser):
    parser.add_argument("kind", nargs=1, default="interactive",
                        choices=["interactive", "single", "batch", "long"])
    parser.add_argument("--command", "-x")


def check_args(args):
    if not args.command and args.kind in ["single", "batch", "long"]:
        print >>sys.stderr, "ERROR: {0} requires that you specify a command."
        return False
    elif args.config:
        print >>sys.stderr, "ERROR: The winrs command does not support " \
                            "a configuration file at this time."
        return False
    return True

if __name__ == '__main__':
    app.main(tx_main, add_args, check_args)
