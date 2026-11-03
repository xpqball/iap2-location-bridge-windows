# Contributing

Use Python 3.11 or later and uv:

```sh
uv sync --locked
uv run ruff check src tests tools
uv run pytest -p no:xonsh -q
```

Run `make native` only on macOS with Apple Command Line Tools. Protocol tests use
local loopback sockets. Authentication tests generate temporary synthetic keys
and certificates; no phone or real accessory identity is needed.

Keep protocol changes covered by interoperability-focused tests: malformed
frames, fragmentation, retransmission, sequence wrap, subscription handling,
and cryptographic encoding. Do not add captured sessions or real credentials as
fixtures. Use artificial data and remove device identifiers from issue reports.

Keep user instructions in the README, protocol details in `docs/protocol.md`,
and helper integration details in `docs/authentication.md`.

Windows tests verify actual NTFS ACLs rather than POSIX mode bits. The symlink
test may skip when Developer Mode or the required privilege is unavailable.
When running elevated, pass `--basetemp` with a new dedicated directory so
administrator and ordinary sessions do not share pytest's default temporary root.
Keep local experiment reports, APKs, pairing records, and environment directories
out of commits. Do not interpret protocol acknowledgements as proof that the
phone adopted a location; real-device reports must state how that was observed.
