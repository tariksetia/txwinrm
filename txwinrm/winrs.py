##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from pprint import pprint
from argparse import ArgumentParser
from .shell import WinrsClient


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--config", "-c")
    parser.add_argument("--remote", "-r")
    parser.add_argument("--username", "-u")
    parser.add_argument("--password", "-p")
    parser.add_argument("--command", "-x")
    return parser.parse_args()


def main():
    args = parse_args()
    client = WinrsClient(args.hostname, args.username, args.password)
    results = client.run_commands(
        [r'typeperf "\Processor(_Total)\% Processor Time" -sc 1'])
    pprint(results)

if __name__ == '__main__':
    main()
