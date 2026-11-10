# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately
through [GitHub Security Advisories](https://github.com/VladimirKrokhin/mbtk/security/advisories/new)
or by email to `krokhinvladimir2004@gmail.com`.

Include the affected version, a minimal reproduction, and the impact you
expect. You will get an answer as soon as possible.

## Scope

The toolkit handles bot tokens, webhook updates, media downloads, and Redis
keys. When reporting, please consider:

- token or secret leakage in logs and exception messages;
- unsafe media URLs (scheme, host, redirects, size limits);
- update parsing that could bypass filters or route an event incorrectly;
- Redis key injection or claim races.

Never include real bot tokens or production update bodies in a report.
