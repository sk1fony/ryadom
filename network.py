"""Prefer a real LAN adapter over a VPN's default route."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
import sys


@dataclass
class Address:
    ip: str
    name: str = ""
    physical: bool = False
    gateway: bool = False


VIRTUAL = re.compile(r"vpn|utun|wintun|wireguard|tailscale|zerotier|vmnet|vmware|vbox|vnic|parallels|docker|hyper-v|vethernet|virtual|loopback|^tun\d|^tap\d|^wg\d|^br-|^bridge|^veth", re.I)


def rank_addresses(records: list[Address]) -> list[str]:
    ranked = []
    for order, record in enumerate(records):
        try:
            address = ipaddress.IPv4Address(record.ip)
        except ipaddress.AddressValueError:
            continue
        if address.is_loopback or address.is_unspecified or address.is_multicast:
            continue
        if VIRTUAL.search(record.name):
            tier = 5
        elif record.physical:
            tier = 0 if record.gateway else 1
        elif record.gateway and record.name:
            tier = 2
        else:
            tier = 3
        if address.is_link_local:
            tier = 6
        # Only a fallback tie-breaker: a physical 10.x LAN still outranks a
        # virtual or unidentified 192.168.x address.
        private_home = 0 if record.ip.startswith("192.168.") else 1
        ranked.append(((tier, private_home, order), record.ip))
    return list(dict.fromkeys(ip for _, ip in sorted(ranked)))


def command(args: list[str], timeout=4) -> str:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=True).stdout


def parse_macos_ifconfig(text: str, hardware: set[str]) -> list[Address]:
    records = []
    blocks = re.split(r"(?m)^(?=\S[^\n]*: flags=)", text)
    for block in blocks:
        match = re.match(r"([^\s:]+):", block)
        if not match or re.search(r"status:\s*inactive", block):
            continue
        name = match[1]
        physical = name in hardware or bool(re.fullmatch(r"en\d+", name))
        for ip in re.findall(r"\binet\s+(\d+\.\d+\.\d+\.\d+)", block):
            records.append(Address(ip, name, physical))
    return records


def parse_windows_config(text: str) -> list[Address]:
    data = json.loads(text.lstrip("\ufeff"))
    if isinstance(data, dict):
        data = [data]
    records = []
    for item in data or []:
        ips = item.get("Addresses") or []
        if isinstance(ips, str):
            ips = [ips]
        for ip in ips:
            records.append(Address(ip, str(item.get("Name", "")), bool(item.get("Physical")), bool(item.get("Gateway"))))
    return records


def local_addresses() -> list[str]:
    records = []
    if sys.platform == "win32":
        script = (
            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
            "Get-NetIPConfiguration -All | ForEach-Object { "
            "[PSCustomObject]@{Name=($_.InterfaceAlias+' '+$_.InterfaceDescription); "
            "Physical=[bool]$_.NetAdapter.HardwareInterface; "
            "Gateway=[bool]$_.IPv4DefaultGateway; "
            "Addresses=@($_.IPv4Address.IPAddress)} } | ConvertTo-Json -Compress -Depth 4"
        )
        with contextlib.suppress(OSError, ValueError, TypeError, subprocess.SubprocessError):
            records.extend(parse_windows_config(command(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=6)))
        if not records:
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                output = command(["ipconfig"])
                records.extend(Address(ip) for ip in re.findall(r"IPv4[^\r\n:]*:\s*(\d+\.\d+\.\d+\.\d+)", output))
    elif sys.platform == "darwin":
        hardware = set()
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            hardware = set(re.findall(r"Device:\s*(\S+)", command(["/usr/sbin/networksetup", "-listallhardwareports"])))
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            records.extend(parse_macos_ifconfig(command(["/sbin/ifconfig"]), hardware))
    else:
        gateways = set()
        with contextlib.suppress(OSError, ValueError, subprocess.SubprocessError):
            gateways = {r.get("dev") for r in json.loads(command(["ip", "-j", "-4", "route", "show", "default"]))}
        with contextlib.suppress(OSError, ValueError, TypeError, subprocess.SubprocessError):
            for interface in json.loads(command(["ip", "-j", "-4", "addr", "show"])):
                name = interface.get("ifname", "")
                if interface.get("operstate") == "DOWN":
                    continue
                physical = bool(re.fullmatch(r"[a-zA-Z0-9_.-]+", name)) and (Path("/sys/class/net") / name / "device").exists()
                physical |= bool(re.match(r"^(eth\d|en[a-z0-9]|wl[a-z0-9])", name))
                for item in interface.get("addr_info", []):
                    if item.get("family") == "inet":
                        records.append(Address(item.get("local", ""), name, physical, name in gateways))
    # Keep fallbacks for systems without the platform utilities. Adapter data,
    # when available, always ranks above the VPN-controlled default route.
    with contextlib.suppress(OSError):
        records.extend(Address(ip) for ip in socket.gethostbyname_ex(socket.gethostname())[2])
    with contextlib.suppress(OSError):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            records.append(Address(sock.getsockname()[0]))
    return rank_addresses(records)
