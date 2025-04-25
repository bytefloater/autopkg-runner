import argparse
import ipaddress
from pathlib import Path
from pprint import pprint
import re
import socket
import subprocess

import dns.resolver
from zeroconf import Zeroconf

from __info__ import RESOLV_CONF


class ZeroConfigResolver:
    def __init__(self):
        self.resolv_conf: Path  = Path(RESOLV_CONF)
        self.domains: list[str] = ['local'] + self.get_search_domains()

    def get_search_domains(self) -> list[str]:
        """
        Retrieve macOS-configured DNS search domains via `scutil --dns`.
        Falls back to parsing /etc/resolv.conf if scutil fails.
        """
        domains: list[str] = []

        try:
            output = subprocess.check_output(['scutil', '--dns'], text=True)
            domains = re.findall(r'search domain\[\d+\] : (.+)', output)
        except subprocess.SubprocessError:
            pass

        if not domains and self.resolv_conf.exists():
            with self.resolv_conf.open('r', encoding='ascii') as f:
                for line in f:
                    if line.startswith('search'):
                        parts = line.split()
                        domains = parts[1:]
                        break

        return domains


    def lookup_mdns(self, name: str, service_type: str, timeout: int = 3000) -> dict[str, any]:
        """
        Perform multicast DNS (mDNS) lookup using zeroconf for a .local service.
        """
        zeroconf = Zeroconf()
        try:
            full_type = f"{service_type}.local."
            full_name = f"{name}.{service_type}.local."
            svc_info = zeroconf.get_service_info(full_type, full_name, timeout=timeout)

            if not svc_info:
                return {'error': 'no mDNS response'}

            addresses = [socket.inet_ntoa(addr) for addr in svc_info.addresses]
            properties = {k.decode(): v for k, v in svc_info.properties.items()}

            return {
                'addresses': addresses,
                'port': svc_info.port,
                'server': svc_info.server.rstrip('.'),
                'properties': properties,
            }
        finally:
            zeroconf.close()


    def lookup_unicast(self, service_fqdn: str) -> dict[str, any]:
        """
        Perform unicast DNS resolution for a given SRV FQDN, including A/AAAA lookups.
        """
        try:
            srv_rr = dns.resolver.resolve(service_fqdn, 'SRV')[0]
            target = str(srv_rr.target).rstrip('.')
            port = srv_rr.port

            addresses: list[str] = []
            for record in ('A'):
                try:
                    for r in dns.resolver.resolve(target, record):
                        addresses.append(r.address)
                except dns.resolver.NoAnswer:
                    continue

            return {
                'target': target,
                'port': port,
                'addresses': addresses,
            }
        except Exception as err:
            return {'error': str(err)}


    def resolve_service(self, name: str, service_type: str, timeout: int = 3000) -> dict[str, dict[str, any]]:
        """
        Resolve a DNS-SD service instance across mDNS (.local) and each search domain.

        :param name: Service instance name
        :param service_type: DNS-SD service type (e.g., "_smb._tcp")
        :param timeout: Milliseconds to wait for mDNS responses
        :return: Mapping of domain to resolution info or error
        """
        results: dict[str, dict[str, any]] = {}

        for domain in self.domains:
            if domain == 'local':
                results[domain] = self.lookup_mdns(name, service_type, timeout)
            else:
                fqdn = f"{name}.{service_type}.{domain}"
                results[domain] = self.lookup_unicast(fqdn)

        return results
    
    def pick_best_result(self, results: dict[str, dict[str, any]]) -> dict[str, any]:
        """
        Given per-domain resolution results, pick a single result according to:
        1. If no lookups succeeded, return an error.
        2. If exactly one domain succeeded, return that result.
        3. If multiple succeeded:
            a. Compute the intersection of all their 'addresses' lists.
            b. If the intersection is non-empty, merge into one result (using the `.local`
                entry when available) but only keep the common addresses.
            c. If there is no overlap, prefer the `.local` result; otherwise pick the first.
        """

        valid = {domain: info for domain, info in results.items() if 'error' not in info}
        if not valid:
            return {'error': 'all lookups failed'}

        if len(valid) == 1:
            return next(iter(valid.values()))

        # 4) Multiple successes: intersect their address sets
        # Start with the first domain's addresses
        iterator = iter(valid.values())
        first_info = next(iterator)
        addr_sets: set[str] = set(first_info.get('addresses', []))

        # Intersect with the rest
        for info in iterator:
            addr_sets &= set(info.get('addresses', []))

        # If there's a common address, merge into one result
        if addr_sets:
            # Choose .local as the primary if available
            primary = valid.get('local', first_info)
            best = primary.copy()
            best['addresses'] = list(addr_sets)
            return best

        # No overlap: prefer .local, else pick the first valid result
        return valid.get('local') or next(iter(valid.values()))

def is_ipv4(address: str) -> bool:
    """
    Return True if `address` is a valid IPv4 address, False otherwise.
    """
    try:
        return isinstance(ipaddress.ip_address(address), ipaddress.IPv4Address)
    except ValueError:
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Zero-config Module for AutoPkg Runner"
    )
    parser.add_argument(
        "-n", "--name",
        required=True,
        help="name of the service instance"
    )
    parser.add_argument(
        "-t", "--type",
        default="_smb._tcp",
        help="zero-config service type (default: '_smb._tcp')"
    )

    args = parser.parse_args()
    resolver = ZeroConfigResolver()
    result = resolver.resolve_service(
        name=args.name,
        service_type=args.type
    )
    print("Result:")
    pprint(result)
    print("\nBest result:")
    print(resolver.pick_best_result(result))
