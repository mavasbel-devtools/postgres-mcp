# postgres-mcp

Source: [mavasbel-devtools/postgres-mcp](https://github.com/mavasbel-devtools/postgres-mcp) · default branch `main`

![language](https://img.shields.io/badge/language-TypeScript-Python-blue) ![status](https://img.shields.io/badge/status-active-brightgreen)

> Read-only-by-default PostgreSQL MCP server with a layered write gate (pglast + read-only transaction + least-privilege role).

## Features

- Read-only by default: every write passes an explicit layered gate
- SQL parsed with pglast, executed in a read-only transaction under a least-privilege role
- Gives AI agents safe, auditable access to Postgres

## Quickstart (< 5 min)

Prerequisite: Python 3 + a PostgreSQL instance (see repo docs for setup).

```sh
git clone https://github.com/mavasbel-devtools/postgres-mcp
```

Then follow the in-repo setup docs (the live README is the authoritative guide); the clone above is the only command this draft asserts — install steps live with the code so they cannot drift.

## Install

Status: notes — no install commands duplicated here. Toolchain: Python 3 + a PostgreSQL instance (see repo docs for setup). See the repository docs for the exact steps.

## Usage

See the repository docs and examples for current usage; this draft only maps the repo, it does not duplicate its manual.

## Structure

See the repository tree on GitHub ([mavasbel-devtools/postgres-mcp](https://github.com/mavasbel-devtools/postgres-mcp)) for the current layout.

## Contributing

Issues and pull requests welcome on GitHub.

## License: GPL-3.0 (evidenced in Stage-1 license audit).

## Links

- Repo: https://github.com/mavasbel-devtools/postgres-mcp
- Owner: https://github.com/mavasbel-devtools
