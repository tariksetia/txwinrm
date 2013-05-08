##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

import os
from xml.etree import cElementTree as ET


def create_get_elem_func(datadir):

    def get_elem(filename):
        with open(os.path.join(datadir, filename)) as f:
            return ET.fromstring(f.read())

    return get_elem
