# The `localhost` trap: a 10-second database connection on Windows

**TL;DR** On Windows, `localhost` resolves to IPv6 `::1` first. A Docker
Postgres that publishes its port on IPv4 only has nothing listening on `::1`, so
each connection hangs until the OS times out and falls back to IPv4: ~10 seconds,
every query. The fix is one word of intent. Connect to `127.0.0.1` instead of
`localhost`, and always set a connect timeout.

## The symptom

Every question in the app took ~15 seconds. Answers were correct. It was just
inexplicably slow, and only on Windows. Nothing in the code looked wrong.

## How we found it (the useful part)

We didn't guess. Two cheap pieces of observability pinned it in minutes:

1. **Per-stage timing.** We split each request into `connect / retrieval /
   generation`. The line read:
   `retrieval 2.1s · generation 3.4s · connect + overhead 10.2s`. Retrieval plus
   generation was only ~5.5s, so 10 seconds was hiding around the DB
   connection, not in the model.
2. **A health check.** A small panel that pings the DB and shows the round-trip:
   `DB reachable · 10137 ms`. Unambiguous: the *connection itself* took 10.1s.

The bug had been there for days behind a vague "it's just slow." The moment we
measured, it took one screenshot to locate.

## The cause

```mermaid
flowchart TD
    S[db.connect] --> Q{host in DATABASE_URL}
    Q -->|localhost| I6["tries IPv6 ::1:5433 first"]
    I6 --> H["Docker publishes IPv4 only -<br/>nothing is listening on ::1,<br/>and no connect_timeout is set"]
    H --> FB["OS eventually gives up,<br/>retries over IPv4"]
    FB --> OK1["connected - ~10 s wasted"]
    Q -->|127.0.0.1| OK2["connected in ~27 ms"]
```

Three things line up to make it hurt:

- **`localhost` is dual-stack** and, on Windows, prefers IPv6 `::1`.
- **Docker's published port is IPv4-only.** The IPv4 loopback answers, `::1` does
  not.
- **No `connect_timeout`**, so the client waits on the dead IPv6 route instead of
  failing fast.

## Before / after

| host | connect latency |
|---|---|
| `localhost` (IPv6 detour) | **10,137 ms** |
| `127.0.0.1` (direct IPv4) | **27 ms** |

About 375× faster, one word changed.

## The fix

- Use **`127.0.0.1`** in the connection string. It's identical on Linux/macOS, where
  loopback is loopback.
- Add a **`connect_timeout`** so a bad route fails in seconds, not minutes. A hang
  is worse than an error.

```bash
# .env
DATABASE_URL=postgresql://user:pass@127.0.0.1:5433/mydb
```

```python
psycopg.connect(DATABASE_URL, connect_timeout=10)
```

## Takeaways

1. **`localhost` ≠ `127.0.0.1`** once IPv6 is in play. For a container mapped to
   IPv4, prefer the literal address.
2. **Always set a connect timeout.** Silent hangs are the hardest bugs to see;
   fail fast and loud.
3. **Cheap observability pays for itself.** A per-stage timer and a one-line health
   check turned a multi-day "it's just slow" into a five-minute fix.
