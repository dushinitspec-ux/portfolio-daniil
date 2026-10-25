"""Device discovery without raw sockets or admin rights.

1. Ping sweep with the system `ping` command, many at a time (a semaphore caps it).
2. Read the neighbour table (`arp -a` / `ip neigh`). Pinging an address makes the OS
   resolve its MAC, so a device that drops ICMP (Windows firewall does by default) still
   shows up here.
3. TCP connect to a short list of ports on every host that answered, to see which services
   accept connections. Nothing is sent after the connection is made.
4. Reverse DNS for a host name, where the local DNS server has one.
"""

import asyncio
import contextlib
import ipaddress
import logging
import socket
from collections.abc import Awaitable, Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from app.parsing import decode, neighbour_command, parse_neighbours, parse_ping, ping_command
from app.scope import Scope

logger = logging.getLogger("inventory.discovery")

MAX_HOSTNAME = 253


@dataclass(frozen=True)
class Observation:
    """One device as seen in one scan."""

    ip: str
    mac: str | None = None
    hostname: str | None = None
    open_ports: frozenset[int] = frozenset()
    answered_ping: bool = False


class Scanner(Protocol):
    async def scan(self, scope: Scope) -> list[Observation]: ...


async def run_command(args: list[str], timeout_s: float) -> tuple[int, str]:
    """(exit code, ASCII-decoded output). A missing command or a hang gives (-1, "")."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    except OSError as exc:
        logger.warning("Cannot run %s: %s", args[0], exc.__class__.__name__)
        return -1, ""
    try:
        output, _ = await asyncio.wait_for(proc.communicate(), timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, ""
    return proc.returncode or 0, decode(output)


async def ping(host: str, timeout_s: float) -> bool:
    returncode, output = await run_command(ping_command(host, timeout_s), timeout_s + 5)
    return parse_ping(returncode, output)


async def read_neighbours() -> dict[str, str]:
    _, output = await run_command(neighbour_command(), timeout_s=10)
    return parse_neighbours(output)


async def tcp_open(host: str, port: int, timeout_s: float) -> bool:
    """True if the port accepted a TCP connection. The connection is closed at once."""
    try:
        async with asyncio.timeout(timeout_s):
            _, writer = await asyncio.open_connection(host, port)
    except (TimeoutError, OSError):
        return False
    writer.close()
    with contextlib.suppress(OSError):
        await writer.wait_closed()
    return True


def clean_hostname(name: str, ip: str) -> str | None:
    """Reverse DNS answers come from the network, so keep them short and printable."""
    name = name.strip().rstrip(".")
    if not name or name == ip or len(name) > MAX_HOSTNAME or not name.isprintable():
        return None
    return name


def system_reverse_lookup(ip: str) -> str:
    """Blocking reverse lookup; raises OSError when the address has no name."""
    name, _ = socket.getnameinfo((ip, 0), socket.NI_NAMEREQD)
    return name


class ReverseDns:
    """Reverse lookups in a thread pool of their own.

    `getnameinfo` blocks and cannot be cancelled. On Windows a lookup for an address without
    a name takes about 5 s to fail. A timeout only stops waiting; the thread keeps going.
    So a slot is freed when the thread really finishes, not when the timeout fires.
    Otherwise the next lookups queue behind busy threads and time out before they start.
    """

    def __init__(
        self,
        workers: int = 32,
        timeout_s: float = 2.0,
        resolve: Callable[[str], str] = system_reverse_lookup,
    ) -> None:
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rdns")
        self._slots = asyncio.Semaphore(workers)
        self._timeout = timeout_s
        self._resolve = resolve

    def _release(self, future: asyncio.Future[str]) -> None:
        self._slots.release()
        if not future.cancelled():
            future.exception()  # mark it as retrieved: nobody may be waiting any more

    async def lookup(self, ip: str) -> str | None:
        await self._slots.acquire()
        future = asyncio.get_running_loop().run_in_executor(self._pool, self._resolve, ip)
        future.add_done_callback(self._release)
        try:
            # shield: a timeout must not cancel the future, or its slot would be freed early.
            name = await asyncio.wait_for(asyncio.shield(future), self._timeout)
        except (TimeoutError, OSError, UnicodeError):
            return None
        return clean_hostname(name, ip)

    async def lookup_all(self, ips: Iterable[str]) -> list[str | None]:
        return await asyncio.gather(*(self.lookup(ip) for ip in ips))


def sort_key(ip: str) -> int:
    return int(ipaddress.IPv4Address(ip))


async def gather_limited[T](limit: int, jobs: Iterable[Callable[[], Awaitable[T]]]) -> list[T]:
    semaphore = asyncio.Semaphore(limit)

    async def run(job: Callable[[], Awaitable[T]]) -> T:
        async with semaphore:
            return await job()

    return await asyncio.gather(*(run(job) for job in jobs))


class NetworkScanner:
    def __init__(
        self,
        ports: Iterable[int],
        *,
        ping_timeout_s: float = 1.0,
        tcp_timeout_s: float = 1.0,
        dns_timeout_s: float = 2.0,
        max_parallel_pings: int = 64,
        max_parallel_connects: int = 128,
        reverse_dns: bool = True,
        pinger: Callable[[str, float], Awaitable[bool]] = ping,
        neighbours: Callable[[], Awaitable[dict[str, str]]] = read_neighbours,
    ) -> None:
        self.ports = tuple(sorted(set(ports)))
        self._ping_timeout = ping_timeout_s
        self._tcp_timeout = tcp_timeout_s
        self._dns = ReverseDns(timeout_s=dns_timeout_s) if reverse_dns else None
        self._max_pings = max_parallel_pings
        self._max_connects = max_parallel_connects
        self._ping = pinger
        self._neighbours = neighbours

    async def scan(self, scope: Scope) -> list[Observation]:
        hosts = list(scope.hosts())
        replies = await gather_limited(
            self._max_pings, [lambda h=h: self._ping(h, self._ping_timeout) for h in hosts]
        )
        answered = {host for host, ok in zip(hosts, replies, strict=True) if ok}
        # Read the table after the sweep: the pings are what filled it.
        macs = {ip: mac for ip, mac in (await self._neighbours()).items() if scope.contains(ip)}
        alive = sorted(answered | set(macs), key=sort_key)

        probes = [(ip, port) for ip in alive for port in self.ports]
        results = await gather_limited(
            self._max_connects,
            [lambda ip=ip, p=p: tcp_open(ip, p, self._tcp_timeout) for ip, p in probes],
        )
        open_ports: dict[str, set[int]] = {ip: set() for ip in alive}
        for (ip, port), is_open in zip(probes, results, strict=True):
            if is_open:
                open_ports[ip].add(port)

        names = await self._dns.lookup_all(alive) if self._dns else [None] * len(alive)

        logger.info(
            "Scanned %d addresses: %d answered ping, %d in the neighbour table, %d alive.",
            len(hosts),
            len(answered),
            len(macs),
            len(alive),
        )
        return [
            Observation(
                ip=ip,
                mac=macs.get(ip),
                hostname=name,
                open_ports=frozenset(open_ports[ip]),
                answered_ping=ip in answered,
            )
            for ip, name in zip(alive, names, strict=True)
        ]
