"""Tests for libs.mdns: is_ipv4, ZeroConfigResolver.pick_best_result."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock


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


# -- ZeroConfigResolver.__init__ and get_search_domains -----------------------

class TestGetSearchDomains:
    def _resolver_bare(self, resolv_conf_path=None):
        """Create a resolver bypassing __init__ to set resolv_conf manually."""
        from libs.mdns import ZeroConfigResolver
        r = ZeroConfigResolver.__new__(ZeroConfigResolver)
        r.resolv_conf = Path(resolv_conf_path or '/dev/null/nonexistent')
        return r

    def test_scutil_success_extracts_domains(self):
        r = self._resolver_bare()
        scutil_out = 'search domain[0] : corp.example.com\nsearch domain[1] : local\n'
        with patch('subprocess.check_output', return_value=scutil_out):
            domains = r.get_search_domains()
        assert any(d == 'corp.example.com' for d in domains)
        assert any(d == 'local' for d in domains)

    def test_scutil_failure_falls_back_to_resolv_conf(self, tmp_path):
        import subprocess as sp
        rconf = tmp_path / 'resolv.conf'
        rconf.write_text('nameserver 1.1.1.1\nsearch corp.local internal\n')
        r = self._resolver_bare(str(rconf))
        with patch('subprocess.check_output', side_effect=sp.SubprocessError):
            domains = r.get_search_domains()
        assert 'corp.local' in domains
        assert 'internal' in domains

    def test_both_fail_returns_empty(self):
        import subprocess as sp
        r = self._resolver_bare()  # resolv_conf points to nonexistent path
        with patch('subprocess.check_output', side_effect=sp.SubprocessError):
            domains = r.get_search_domains()
        assert domains == []

    def test_resolv_conf_no_search_line(self, tmp_path):
        import subprocess as sp
        rconf = tmp_path / 'resolv.conf'
        rconf.write_text('nameserver 8.8.8.8\n')
        r = self._resolver_bare(str(rconf))
        with patch('subprocess.check_output', side_effect=sp.SubprocessError):
            domains = r.get_search_domains()
        assert domains == []


class TestZeroConfigResolverInit:
    def test_init_sets_domains_with_local(self):
        from libs.mdns import ZeroConfigResolver
        with patch('subprocess.check_output', return_value='search domain[0] : corp.net\n'):
            r = ZeroConfigResolver()
        assert any(d == 'local' for d in r.domains)
        assert any(d == 'corp.net' for d in r.domains)

    def test_init_always_includes_local(self):
        from libs.mdns import ZeroConfigResolver
        import subprocess as sp
        with patch('subprocess.check_output', side_effect=sp.SubprocessError):
            r = ZeroConfigResolver()
        assert r.domains[0] == 'local'


# -- lookup_mdns ---------------------------------------------------------------

class TestLookupMdns:
    def _resolver(self):
        from libs.mdns import ZeroConfigResolver
        r = ZeroConfigResolver.__new__(ZeroConfigResolver)
        r.resolv_conf = Path('/dev/null/nonexistent')
        r.domains = ['local']
        return r

    def test_no_svc_info_returns_error(self):
        r = self._resolver()
        mock_zc = MagicMock()
        mock_zc.get_service_info.return_value = None
        with patch('libs.mdns.Zeroconf', return_value=mock_zc):
            result = r.lookup_mdns('myserver', '_smb._tcp')
        assert 'error' in result
        mock_zc.close.assert_called_once()

    def test_svc_found_returns_dict(self):
        import struct
        r = self._resolver()
        svc = MagicMock()
        # Provide a proper 4-byte packed address for inet_ntoa
        svc.addresses = [struct.pack('!I', (192 << 24) | (168 << 16) | (1 << 8) | 10)]
        svc.port = 445
        svc.server = 'myserver.local.'
        svc.properties = {b'key': b'val'}
        mock_zc = MagicMock()
        mock_zc.get_service_info.return_value = svc
        with patch('libs.mdns.Zeroconf', return_value=mock_zc):
            result = r.lookup_mdns('myserver', '_smb._tcp')
        assert '192.168.1.10' in result['addresses']
        assert result['port'] == 445
        mock_zc.close.assert_called_once()


# -- lookup_unicast ------------------------------------------------------------

class TestLookupUnicast:
    def _resolver(self):
        from libs.mdns import ZeroConfigResolver
        r = ZeroConfigResolver.__new__(ZeroConfigResolver)
        r.domains = ['local']
        return r

    def test_exception_returns_error_dict(self):
        r = self._resolver()
        import dns.resolver
        with patch('dns.resolver.resolve', side_effect=Exception('no SRV')):
            result = r.lookup_unicast('myserver._smb._tcp.corp.net')
        assert 'error' in result
        assert 'no SRV' in result['error']

    def test_success_returns_target_and_addresses(self):
        r = self._resolver()
        mock_srv = MagicMock()
        mock_srv.target = MagicMock()
        mock_srv.target.__str__ = lambda _: 'myserver.corp.net.'
        mock_srv.port = 445
        mock_a = MagicMock()
        mock_a.address = '10.0.0.5'
        with patch('dns.resolver.resolve') as mock_resolve:
            mock_resolve.side_effect = [
                [mock_srv],    # SRV lookup
                [mock_a],      # A lookup
            ]
            result = r.lookup_unicast('myserver._smb._tcp.corp.net')
        assert result.get('port') == 445
        assert '10.0.0.5' in result.get('addresses', [])


# -- resolve_service -----------------------------------------------------------

class TestResolveService:
    def _resolver(self, domains):
        from libs.mdns import ZeroConfigResolver
        r = ZeroConfigResolver.__new__(ZeroConfigResolver)
        r.domains = domains
        return r

    def test_local_domain_uses_lookup_mdns(self):
        r = self._resolver(['local'])
        with patch.object(r, 'lookup_mdns', return_value={'addresses': ['1.2.3.4']}) as mock_mdns:
            results = r.resolve_service('server', '_smb._tcp')
        assert 'local' in results
        mock_mdns.assert_called_once_with('server', '_smb._tcp', 3000)

    def test_non_local_domain_uses_lookup_unicast(self):
        r = self._resolver(['corp.net'])
        with patch.object(r, 'lookup_unicast',
                          return_value={'addresses': ['1.2.3.4']}) as mock_uni:
            results = r.resolve_service('server', '_smb._tcp')
        assert results.get('corp.net') is not None
        mock_uni.assert_called_once_with('server._smb._tcp.corp.net')

    def test_mixed_domains(self):
        r = self._resolver(['local', 'corp.net'])
        mdns_result = {'addresses': ['1.2.3.4']}
        uni_result = {'addresses': ['5.6.7.8']}
        with patch.object(r, 'lookup_mdns', return_value=mdns_result), \
             patch.object(r, 'lookup_unicast', return_value=uni_result):
            results = r.resolve_service('server', '_smb._tcp')
        assert results['local'] == mdns_result
        assert results['corp.net'] == uni_result
