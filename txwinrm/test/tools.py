##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import os
from xml.etree import cElementTree as ET


def create_get_elem_func(datadir):

    def get_elem(filename):
        with open(os.path.join(datadir, filename)) as f:
            return ET.fromstring(f.read())

    return get_elem
