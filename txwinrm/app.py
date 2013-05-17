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
from getpass import getpass
from urlparse import urlparse
from collections import namedtuple
from argparse import ArgumentParser
from ConfigParser import RawConfigParser
from twisted.internet import reactor, defer

logging.basicConfig()
log = logging.getLogger('zen.winrm')
_exit_status = 0
DEFAULT_SCHEME = 'http'
DEFAULT_PORT = 5985

ConnectionInfo = namedtuple(
    'ConnectionInfo',
    ['hostname', 'auth_type', 'username', 'password', 'scheme', 'port'])


class Builder(object):

    def build(self):
        return self._


class BaseUtility(object):

    def tx_main(args, config):
        stop_reactor()

    def add_args(parser):
        pass

    def check_args(args):
        return True

    def add_config(parser, config):
        pass

    def adapt_args_to_config(self, args, config):
        pass


class Config(object):

    def __init__(self, conn_infos=None):
        self.conn_infos = conn_infos


def _parse_remote(remote):
    url_parts = urlparse(remote)
    if url_parts.netloc:
        return url_parts.hostname, url_parts.scheme, url_parts.port
    return remote, DEFAULT_SCHEME, DEFAULT_PORT


def _parse_config_file(filename, utility):
    parser = RawConfigParser(allow_no_value=True)
    parser.read(filename)
    creds = {}
    index = dict(authentication=0, username=1)
    for key, value in parser.items('credentials'):
        k1, k2 = key.split('.')
        if k1 not in creds:
            creds[k1] = [None, None, None]
        creds[k1][index[k2]] = value
        if k2 == 'username':
            creds[k1][2] = getpass('{0} password ({1} credentials):'
                                   .format(value, k1))
    conn_infos = []
    for remote, cred_key in parser.items('remotes'):
        auth_type, username, password = creds[cred_key]
        hostname, scheme, port = _parse_remote(remote)
        conn_infos.append(ConnectionInfo(
            hostname, auth_type, username, password, scheme, port))
    config = Config(conn_infos)
    utility.add_config(parser, config)
    return config


def _parse_args(utility):
    parser = ArgumentParser()
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--config", "-c")
    parser.add_argument("--remote", "-r")
    parser.add_argument("--authentication", "-a", default='basic',
                        choices=['basic', 'kerberos'])
    parser.add_argument("--username", "-u")
    utility.add_args(parser)
    args = parser.parse_args()
    if not args.config:
        if not args.remote or not args.username:
            print >>sys.stderr, "ERROR: You must specify a config file with " \
                                "-c or specify remote and username"
            sys.exit(1)
        if not utility.check_args(args):
            sys.exit(1)
        if args.remote:
            hostname, scheme, port = _parse_remote(args.remote)
            password = getpass()
            args.conn_info = ConnectionInfo(
                hostname, args.authentication, args.username, password, scheme,
                port)
    for attr in 'remote', 'authentication', 'username':
        delattr(args, attr)
    return args


def _adapt_args_to_config(args, utility):
    config = Config([args.conn_info])
    utility.adapt_args_to_config(args, config)
    return config


def main(utility):
    args = _parse_args(utility)
    if args.debug:
        log.setLevel(level=logging.DEBUG)
        defer.setDebugging(True)
    if args.config:
        config = _parse_config_file(args.config, utility)
    else:
        config = _adapt_args_to_config(args, utility)
    reactor.callWhenRunning(utility.tx_main, args, config)
    reactor.run()
    sys.exit(_exit_status)


def stop_reactor(*args, **kwargs):
    if reactor.running:
        reactor.stop()
