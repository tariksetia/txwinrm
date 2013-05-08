#!/usr/bin/env python

##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

from distutils.core import setup

setup(name='txwinrm',
      version='0.9.0',
      description='Asynchronous Python WinRM client',
      author='Zenoss',
      author_email='bedwards@zenoss.com',
      url='https://github.com/zenoss/txwinrm',
      packages=['txwinrm', 'txwinrm.request'],
      package_data={'txwinrm.request': ['*.xml']},
      scripts=['scripts/winrm', 'scripts/winrs', 'scripts/wecutil',
               'scripts/typeperf']
      )
