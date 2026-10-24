# Bugs found and fixed

Real bugs I hit while building this project, in the order I found them. Neither showed up in
the unit tests at first: the first needed a measurement on real Windows, the second a look at
what git would actually commit.

---

## 1. Host names went missing when many addresses had no name

**What broke.** I measured reverse DNS on this machine (Windows 11) before trusting it with a
whole subnet. Alone, `127.0.0.1` resolved to the computer name in 3 ms. In a batch of 61
loopback addresses, where the other 60 have no name, the same lookup came back empty:

```
hosts 61 elapsed 8.03
127.0.0.1 -> None
```

On a real network that means devices losing their host names whenever the subnet has many
addresses without a DNS record, which is the normal case.

**Root cause.** Three things together:

- On Windows a reverse lookup for an address without a name takes **4.98 s** to fail
  (measured: `gaierror 11001` after 4.984 s and 4.986 s).
- `loop.getnameinfo()` runs the blocking call in the default thread pool: 12 threads on this
  8-core machine. `asyncio.wait_for(..., 2)` stops *waiting* after 2 s, but a thread blocked
  in `getnameinfo` cannot be cancelled and stays busy for the full 5 s.
- The semaphore slot was released at the timeout, so new lookups were started while all
  threads were still busy. They sat in the pool's queue, and their 2 s ran out before they
  even began. `127.0.0.1` was last in the queue.

**Fix.** A thread pool of its own for reverse DNS, and a slot is freed only when the thread
really finishes. The timeout still limits how long the scan waits, but every lookup that
starts has a free thread. `asyncio.shield` keeps the timeout from cancelling the future,
which would have freed the slot early again.

```python
# before
async def reverse_dns(ip: str, timeout_s: float) -> str | None:
    loop = asyncio.get_running_loop()
    try:
        name, _ = await asyncio.wait_for(loop.getnameinfo((ip, 0), socket.NI_NAMEREQD), timeout_s)
    except (TimeoutError, OSError):
        return None
    return clean_hostname(name, ip)


names = await gather_limited(16, [lambda ip=ip: reverse_dns(ip, self._dns_timeout) for ip in alive])
```

```python
# after
class ReverseDns:
    def __init__(self, workers=32, timeout_s=2.0, resolve=system_reverse_lookup):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rdns")
        self._slots = asyncio.Semaphore(workers)
        ...

    def _release(self, future):
        self._slots.release()  # only when the thread is really done

    async def lookup(self, ip: str) -> str | None:
        await self._slots.acquire()
        future = asyncio.get_running_loop().run_in_executor(self._pool, self._resolve, ip)
        future.add_done_callback(self._release)
        try:
            name = await asyncio.wait_for(asyncio.shield(future), self._timeout)
        except (TimeoutError, OSError, UnicodeError):
            return None
        return clean_hostname(name, ip)
```

The same measurement after the fix:

```
hosts 61 elapsed 7.04
127.0.0.1 -> Danya
```

A regression test reproduces it without the network: a fake resolver blocks 0.6 s for
"addresses without a name", the timeout is 0.3 s, and the one named address comes last in
the queue. It must still get its name.

**Lesson.** A timeout on a blocking call in a thread does not free the thread. When a
resource is held longer than you wait for it, count the resource, not the wait.

---

## 2. The vendor table would have been left out of every commit

**What broke.** All tests passed, but `git status` did not list the bundled vendor file
`app/data/oui.csv`:

```
$ git check-ignore -v projects/07-network-inventory/app/data/oui.csv
.gitignore:17:data/	projects/07-network-inventory/app/data/oui.csv
```

A fresh clone would have no vendor table, and the app would stop at startup with
`FileNotFoundError` in `OuiDatabase.load()`.

**Root cause.** The repository's `.gitignore` has `data/` so that SQLite databases are never
committed. A pattern without a leading slash matches a directory of that name at any depth,
including `app/data/`. The tests passed because the file was on my disk.

**Fix.** The file moved to `app/resources/`, and a test asks git directly whether any file
the app or the tests need is ignored (`git check-ignore --no-index`), so the same mistake
fails the test suite instead of a fresh clone.

```python
# before
DEFAULT_OUI_FILE = Path(__file__).parent / "data" / "oui.csv"
```

```python
# after
# Not in a "data" directory: the repository ignores those (they hold SQLite files).
DEFAULT_OUI_FILE = Path(__file__).parent / "resources" / "oui.csv"
```

**Lesson.** Green tests on my machine say nothing about what a clone will contain. Check
what git will actually commit, especially for data files.
