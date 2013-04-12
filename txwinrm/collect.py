##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from pprint import pformat
from twisted.internet import defer
from .client import WinrmClientFactory

_MARKER = object()


class AddPropertyWithoutItemError(Exception):

    def __init__(self, msg):
        Exception("It is an illegal state for add_property to be called "
                  "before the first call to new_item. {0}".format(msg))


class Item(object):

    def __repr__(self):
        return '\n' + pformat(vars(self), indent=4)


class ItemsAccumulator(object):

    def __init__(self):
        self.items = []

    def new_item(self):
        self.items.append(Item())

    def add_property(self, name, value):
        if not self.items:
            raise AddPropertyWithoutItemError(
                "{0} = {1}".format(name, value))
        item = self.items[-1]
        prop = getattr(item, name, _MARKER)
        if prop is _MARKER:
            setattr(item, name, value)
            return
        if isinstance(prop, list):
            prop.append(value)
            return
        setattr(item, name, [prop, value])


class WinrmCollectClient(object):

    def __init__(self):
        self._client_factory = WinrmClientFactory()

    @defer.inlineCallbacks
    def do_collect(self, hostname, username, password, wqls):
        client = self._client_factory.create_winrm_client()
        items = {}
        for wql in wqls:
            accumulator = ItemsAccumulator()
            yield client.enumerate(hostname, username, password, wql,
                                   accumulator)
            items[wql] = accumulator.items
        defer.returnValue(items)


# ----- An example of useage...

if __name__ == '__main__':
    from pprint import pprint
    import logging
    from twisted.internet import reactor
    logging.basicConfig()
    winrm = WinrmCollectClient()

    @defer.inlineCallbacks
    def do_example_collect():
        items = yield winrm.do_collect(
            "gilroy", "Administrator", "Z3n0ss",
            ['Select Caption, DeviceID, Name From Win32_Processor',
             'select Name, Label, Capacity from Win32_Volume'])
        pprint(items)
        reactor.stop()

    reactor.callWhenRunning(do_example_collect)
    reactor.run()
