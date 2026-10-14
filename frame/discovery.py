"""Announce the frame on the LAN via mDNS so Home Assistant can discover it."""

from __future__ import annotations

import logging
import socket

log = logging.getLogger("frame.discovery")

SERVICE_TYPE = "_inkyframe._tcp.local."


def _primary_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("10.255.255.255", 1))  # no packet is sent
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


class Announcer:
    def __init__(self, device_id: str, name: str, port: int, version: str):
        self._zc = None
        self._info = None
        try:
            from zeroconf import ServiceInfo, Zeroconf

            self._info = ServiceInfo(
                SERVICE_TYPE,
                f"{name}-{device_id}.{SERVICE_TYPE}",
                addresses=[socket.inet_aton(_primary_ip())],
                port=port,
                properties={"id": device_id, "name": name, "version": version},
                server=f"{socket.gethostname()}.local.",
            )
            self._zc = Zeroconf()
        except Exception:
            log.warning("mDNS announcement unavailable", exc_info=True)

    def register(self) -> None:
        if self._zc and self._info:
            self._zc.register_service(self._info)
            log.info("Announced %s via mDNS", self._info.name)

    def close(self) -> None:
        if self._zc and self._info:
            self._zc.unregister_service(self._info)
            self._zc.close()
