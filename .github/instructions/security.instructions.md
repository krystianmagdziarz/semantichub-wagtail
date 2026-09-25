---
applyTo: "semantichub_wagtail/auth.py,semantichub_wagtail/images.py,semantichub_wagtail/content.py,semantichub_wagtail/views.py,semantichub_wagtail/publish.py"
---

These modules face the internet. Treat every request byte as attacker-controlled
until `auth.py` accepts it, and payload fields as untrusted after that.

- `auth.py`: the HMAC covers `timestamp + "." + request.body` (the raw body,
  never re-serialised JSON); the timestamp is bounded in length and checked
  against the 5 minute window before hashing; empty settings reject.
- `images.py`: only `https` without userinfo; every resolved address passes
  `_is_public` (IPv4-mapped IPv6 unwrapped); the connection is pinned to the
  checked address with the original `Host` and SNI; every redirect hop goes
  back through `_pinned_request`; the redirect count, `MAX_BYTES` and the
  deadline stay enforced; content type and decoded format are both checked
  and SVG is never stored.
- `content.py`: markdown keeps `html: False`; HTML goes through `nh3.clean`;
  no new path returns unsanitised HTML.
- `publish.py`: the service account stays inactive with an unusable password.
- Error responses carry short fixed messages, never secrets, tracebacks or
  echoed payloads.
