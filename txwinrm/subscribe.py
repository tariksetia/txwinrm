##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from .util import get_url_and_headers, send_request

_EVENT_QUERY_FMT = '&lt;QueryList&gt;&lt;Query Path=&quot;{path}&quot;&gt;' \
    '&lt;Select&gt;{select}&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;'


class EventSubscription(object):

    def __init__(self, hostname, username, password):
        self._hostname = hostname
        self._username = username
        self._password = password
        self._url, self._headers = get_url_and_headers(
            hostname, username, password)

    def subscribe(self, path='Application', select='*'):
        event_query = _EVENT_QUERY_FMT.format(path=path, select=select)
        send_request(
            self._url, self._headers, 'subscribe', event_query=event_query)
