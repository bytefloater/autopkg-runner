"""Tests for libs.mdns: is_ipv4, ZeroConfigResolver.pick_best_result."""
from __future__ import annotations

from pathlib import Path


class TestIsIPv4:
    def _call(self, addr):
        from libs.mdns import is_ipv4
        return is_ipv4(addr)

    def test_valid_ipv4(self):
        assert self._call('192.168.1.1') is True
        assert self._call('10.0.0.1') is True
        assert self._call('0.0.0.0') is True

    def test_ipv6_returns_false(self):
        assert self._call('::1') is False
        assert self._call('2001:db8::1') is False

    def test_invalid_string_returns_false(self):
        assert self._call('not-an-ip') is False
        assert self._call('') is False
        assert self._call('999.999.999.999') is False


class TestPickBestResult:
    def _resolver(self):
        from libs.mdns import ZeroConfigResolver
        r = ZeroConfigResolver.__new__(ZeroConfigResolver)
        r.resolv_conf = Path('/dev/null/nonexistent-resolv.conf')
        r.domains = ['local']
        return r

    def test_all_lookups_failed_returns_error(self):
        r = self._resolver()
        results = {'local': {'error': 'no mDNS response'}}
        best = r.pick_best_result(results)
        assert 'error' in best

    def test_single_success_returned_directly(self):
        r = self._resolver()
        info = {'addresses': ['1.2.3.4'], 'port': 445}
        results = {'local': info, 'corp.example.com': {'error': 'failed'}}
        best = r.pick_best_result(results)
        assert best is info

    def test_multiple_successes_overlapping_addresses_merged(self):
        r = self._resolver()
        results = {
            'local':           {'addresses': ['1.2.3.4', '5.6.7.8'], 'port': 445, 'server': 'host.local'},
            'corp.example.com': {'addresses': ['1.2.3.4'], 'port': 445, 'server': 'host.corp'},
        }
        best = r.pick_best_result(results)
        # Only the intersecting address should be kept
        assert best['addresses'] == ['1.2.3.4']

    def test_multiple_successes_prefers_local_when_overlap(self):
        r = self._resolver()
        results = {
            'local':    {'addresses': ['1.2.3.4'], 'port': 445, 'server': 'myserver.local'},
            'corp.net': {'addresses': ['1.2.3.4'], 'port': 445, 'server': 'myserver.corp'},
        }
        best = r.pick_best_result(results)
        assert best.get('server') == 'myserver.local'

    def test_no_overlap_prefers_local(self):
        r = self._resolver()
        results = {
            'local':    {'addresses': ['1.2.3.4'], 'port': 445},
            'corp.net': {'addresses': ['9.9.9.9'], 'port': 445},
        }
        best = r.pick_best_result(results)
        assert best['addresses'] == ['1.2.3.4']
