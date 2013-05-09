#!/usr/bin/env python

##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

from os.path import dirname, abspath, join

BASEDIR = dirname(abspath(__file__))
LONG_DESCRIPTION = open(join(BASEDIR, 'README.rst')).read()
LICENSE = join(BASEDIR, 'LICENSE')

setup_kwargs = dict(
    name='txwinrm',
    version='0.9.0',
    description='Asynchronous Python WinRM client',
    long_description=LONG_DESCRIPTION,
    license=LICENSE,
    author='Zenoss',
    author_email='bedwards@zenoss.com',
    url='https://github.com/zenoss/txwinrm',
    packages=['txwinrm', 'txwinrm.request'],
    package_data={'txwinrm.request': ['*.xml']},
    scripts=[
        'scripts/winrm',
        'scripts/winrs',
        'scripts/wecutil',
        'scripts/typeperf',
        'scripts/genkrb5conf'])

try:
    from setuptools import setup
    setup_kwargs['install_requires'] = ['twisted', 'kerberos']
    try:
        import argparse
        if False:
            argparse
    except ImportError:
        setup_kwargs['install_requires'].append('argparse')
    setup(**setup_kwargs)
except ImportError:
    from distutils.core import setup
    setup(**setup_kwargs)
