##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

from twisted.trial import unittest
from twisted.internet import defer
from .. import app

INITIAL_STATS = {
    'berkeley': [
    {'IDProcess': '1580',
        'Name': 'WmiPrvSE',
        'PercentProcessorTime': '75504484',
        'Timestamp_Sys100NS': '130125266503145012'},

    {'IDProcess': '1744',
        'Name': 'WmiPrvSE#1',
        'PercentProcessorTime': '29952192',
        'Timestamp_Sys100NS': '130125266503145012'},

    {'IDProcess': '3216',
        'Name': 'WmiPrvSE#2',
        'PercentProcessorTime': '3120020',
        'Timestamp_Sys100NS': '130125266503145012'}],
    'fremont': [
    {'IDProcess': '1904',
        'Name': 'wmiprvse',
        'PercentProcessorTime': '1469375000',
        'Timestamp_Sys100NS': '280719748000'},

    {'IDProcess': '256',
        'Name': 'wmiprvse',
        'PercentProcessorTime': '2997812500',
        'Timestamp_Sys100NS': '280719748000'}],
    'gilroy': [
    {'IDProcess': '1392',
        'Name': 'WmiPrvSE',
        'PercentProcessorTime': '68016436',
        'Timestamp_Sys100NS': '130125266508735505'},

    {'IDProcess': '1704',
        'Name': 'WmiPrvSE#1',
        'PercentProcessorTime': '54288348',
        'Timestamp_Sys100NS': '130125266508735505'},

    {'IDProcess': '1468',
        'Name': 'WmiPrvSE#2',
        'PercentProcessorTime': '2340015',
        'Timestamp_Sys100NS': '130125266508735505'}],
    'milpitas': [
    {'IDProcess': '1860',
        'Name': 'wmiprvse',
        'PercentProcessorTime': '1320625000',
        'Timestamp_Sys100NS': '295141036000'},

    {'IDProcess': '424',
        'Name': 'wmiprvse',
        'PercentProcessorTime': '3019531250',
        'Timestamp_Sys100NS': '295141036000'}],
    'oakland': [
    {'IDProcess': '1588',
        'Name': 'WmiPrvSE',
        'PercentProcessorTime': '520887339',
        'Timestamp_Sys100NS': '130125266497964019'},

    {'IDProcess': '1896',
        'Name': 'WmiPrvSE#1',
        'PercentProcessorTime': '3619067199',
        'Timestamp_Sys100NS': '130125266497964019'},

    {'IDProcess': '336',
        'Name': 'WmiPrvSE#2',
        'PercentProcessorTime': '1716011',
        'Timestamp_Sys100NS': '130125266497964019'}],
    'saratoga': [
    {'IDProcess': '1664',
        'Name': 'WmiPrvSE',
        'PercentProcessorTime': '247105584',
        'Timestamp_Sys100NS': '130125266497494532'},

    {'IDProcess': '2008',
        'Name': 'WmiPrvSE#1',
        'PercentProcessorTime': '1969356624',
        'Timestamp_Sys100NS': '130125266497494532'},

    {'IDProcess': '1096',
        'Name': 'WmiPrvSE#2',
        'PercentProcessorTime': '1404009',
        'Timestamp_Sys100NS': '130125266497494532'},

    {'IDProcess': '2772',
        'Name': 'WmiApSrv',
        'PercentProcessorTime': '312002',
        'Timestamp_Sys100NS': '130125266497494532'}]}

FINAL_STATS = {
    'berkeley': [
    {'IDProcess': '1580',
        'Name': 'WmiPrvSE',
        'PercentProcessorTime': '75504484',
        'Timestamp_Sys100NS': '130125266605946376'},

    {'IDProcess': '1744',
        'Name': 'WmiPrvSE#1',
        'PercentProcessorTime': '31824204',
        'Timestamp_Sys100NS': '130125266605946376'},

    {'IDProcess': '3216',
        'Name': 'WmiPrvSE#2',
        'PercentProcessorTime': '3744024',
        'Timestamp_Sys100NS': '130125266605946376'}],
    'fremont': [
    {'IDProcess': '1904',
        'Name': 'wmiprvse',
        'PercentProcessorTime': '1471406250',
        'Timestamp_Sys100NS': '280823171000'},

    {'IDProcess': '256',
        'Name': 'wmiprvse',
        'PercentProcessorTime': '2998750000',
        'Timestamp_Sys100NS': '280823171000'}],
    'gilroy': [
    {'IDProcess': '1392',
        'Name': 'WmiPrvSE',
        'PercentProcessorTime': '68016436',
        'Timestamp_Sys100NS': '130125266620118791'},

    {'IDProcess': '1704',
        'Name': 'WmiPrvSE#1',
        'PercentProcessorTime': '54756351',
        'Timestamp_Sys100NS': '130125266620118791'},

    {'IDProcess': '1468',
        'Name': 'WmiPrvSE#2',
        'PercentProcessorTime': '2808018',
        'Timestamp_Sys100NS': '130125266620118791'}],
    'milpitas': [
    {'IDProcess': '1860',
        'Name': 'wmiprvse',
        'PercentProcessorTime': '1321718750',
        'Timestamp_Sys100NS': '295253707000'},

    {'IDProcess': '424',
        'Name': 'wmiprvse',
        'PercentProcessorTime': '3020000000',
        'Timestamp_Sys100NS': '295253707000'}],
    'oakland': [
    {'IDProcess': '1588',
        'Name': 'WmiPrvSE',
        'PercentProcessorTime': '521979346',
        'Timestamp_Sys100NS': '130125266609972832'},

    {'IDProcess': '1896',
        'Name': 'WmiPrvSE#1',
        'PercentProcessorTime': '3627335252',
        'Timestamp_Sys100NS': '130125266609972832'},

    {'IDProcess': '336',
        'Name': 'WmiPrvSE#2',
        'PercentProcessorTime': '2496016',
        'Timestamp_Sys100NS': '130125266609972832'},

    {'IDProcess': '304',
        'Name': 'WmiApSrv',
        'PercentProcessorTime': '156001',
        'Timestamp_Sys100NS': '130125266609972832'}],
    'saratoga': [
    {'IDProcess': '1664',
        'Name': 'WmiPrvSE',
        'PercentProcessorTime': '248977596',
        'Timestamp_Sys100NS': '130125266601547272'},

    {'IDProcess': '2008',
        'Name': 'WmiPrvSE#1',
        'PercentProcessorTime': '1970604632',
        'Timestamp_Sys100NS': '130125266601547272'},

    {'IDProcess': '1096',
        'Name': 'WmiPrvSE#2',
        'PercentProcessorTime': '2184014',
        'Timestamp_Sys100NS': '130125266601547272'},

    {'IDProcess': '2772',
        'Name': 'WmiApSrv',
        'PercentProcessorTime': '312002',
        'Timestamp_Sys100NS': '130125266601547272'}]}

EXPECTED_CPU_UTIL_INFO = [
    ['milpitas',
     [(0.009707466872575907, 'wmiprvse', '1860'),
      (0.0041603429453896746, 'wmiprvse', '424')]],
    ['saratoga',
     [(0.017990992567461176, 'WmiPrvSE', '1664'),
      (0.011993995044974119, 'WmiPrvSE#1', '2008'),
      (0.007496246903108824, 'WmiPrvSE#2', '1096'),
      (0.0, 'WmiApSrv', '2772')]],
    ['fremont',
     [(0.01964021542596908, 'wmiprvse', '1904'),
      (0.009064714811985728, 'wmiprvse', '256')]],
    ['berkeley',
     [(0.0, 'WmiPrvSE', '1580'),
      (0.01820999255262771, 'WmiPrvSE#1', '1744'),
      (0.006069997517542569, 'WmiPrvSE#2', '3216')]],
    ['oakland',
     [(0.009749295091200679, 'WmiPrvSE', '1588'),
      (0.07381609140480513, 'WmiPrvSE#1', '1896'),
      (0.006963782208000485, 'WmiPrvSE#2', '336')]],
    ['gilroy',
     [(0.0, 'WmiPrvSE', '1392'),
      (0.0042017347666543844, 'WmiPrvSE#1', '1704'),
      (0.0042017347666543844, 'WmiPrvSE#2', '1468')]]]


class Client(object):

    def enumerate(self, wql):
        return defer.succeed("foo")


class FakeItem(object):
    pass


def convert_stats(stats_with_dicts):
    new_stats = {}
    for key, dcts in stats_with_dicts.iteritems():
        new_stats[key] = []
        for dct in dcts:
            item = FakeItem()
            item.IDProcess = dct['IDProcess']
            item.Name = dct['Name']
            item.PercentProcessorTime = dct['PercentProcessorTime']
            item.Timestamp_Sys100NS = dct['Timestamp_Sys100NS']
            new_stats[key].append(item)
    return new_stats


class TestApp(unittest.TestCase):

    def test_get_vmpeak(self):
        actual = app.get_vmpeak()
        self.assertIsNotNone(actual)

    @defer.inlineCallbacks
    def test_get_remote_process_stats(self):
        actual = yield app.get_remote_process_stats(Client())
        self.assertEqual(actual, 'foo')

    def test_calculate_remote_cpu_util(self):
        initial = convert_stats(INITIAL_STATS)
        final = convert_stats(FINAL_STATS)
        actual = app.calculate_remote_cpu_util(initial, final)
        self.assertEqual(actual, EXPECTED_CPU_UTIL_INFO)

if __name__ == '__main__':
    unittest.main()
