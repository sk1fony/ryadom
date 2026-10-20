import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from network import Address, parse_macos_ifconfig, parse_windows_config, rank_addresses


class AddressTests(unittest.TestCase):
    def test_macos_vpn_and_parallels_do_not_replace_wifi(self):
        config = """utun4: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1500
        inet 10.0.0.2 --> 10.0.0.2 netmask 0xffffffff
vnic0: flags=8843<UP,BROADCAST,RUNNING,MULTICAST> mtu 1500
        inet 10.211.55.2 netmask 0xffffff00
vnic1: flags=8843<UP,BROADCAST,RUNNING,MULTICAST> mtu 1500
        inet 10.37.129.2 netmask 0xffffff00
en0: flags=8863<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> mtu 1500
        inet 192.168.1.9 netmask 0xffffff00 broadcast 192.168.1.255
        status: active
en1: flags=8863<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> mtu 1500
        inet 192.168.99.2 netmask 0xffffff00
        status: inactive
"""
        addresses = rank_addresses(parse_macos_ifconfig(config, {"en0", "en1"}))
        self.assertEqual(addresses[0], "192.168.1.9")
        self.assertEqual(set(addresses), {"192.168.1.9", "10.0.0.2", "10.211.55.2", "10.37.129.2"})

    def test_real_10_network_is_preferred_over_a_virtual_192_network(self):
        records = [Address("192.168.56.1", "VirtualBox", False, True), Address("10.20.30.40", "Wi-Fi", True, True), Address("192.168.1.3")]
        self.assertEqual(rank_addresses(records)[0], "10.20.30.40")

    def test_windows_physical_adapter_metadata(self):
        data = json.dumps([
            {"Name": "Wintun VPN", "Physical": False, "Gateway": True, "Addresses": ["10.0.0.2"]},
            {"Name": "Wi-Fi Intel", "Physical": True, "Gateway": True, "Addresses": ["192.168.1.9"]},
            {"Name": "Ethernet", "Physical": True, "Gateway": False, "Addresses": ["172.16.0.4"]},
        ])
        self.assertEqual(rank_addresses(parse_windows_config(data)), ["192.168.1.9", "172.16.0.4", "10.0.0.2"])

    def test_fallback_deduplicates_and_prefers_home_lan(self):
        records = [Address("10.0.0.2"), Address("192.168.1.9"), Address("127.0.0.1"), Address("0.0.0.0"), Address("bad"), Address("192.168.1.9"), Address("169.254.1.2")]
        self.assertEqual(rank_addresses(records), ["192.168.1.9", "10.0.0.2", "169.254.1.2"])


if __name__ == "__main__":
    unittest.main()
