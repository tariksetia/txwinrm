#!/usr/bin/env python

##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from distutils.core import setup

setup(name='txwinrm',
      version='0.2',
      description='Asynchronous Python WinRM client',
      author='Zenoss',
      author_email='bedwards@zenoss.com',
      url='https://github.com/zenoss/txwinrm',
      packages=['txwinrm', 'txwinrm.request'],
      package_data={'txwinrm.request': ['*.xml']},
      scripts=['scripts/winrm']
      )
