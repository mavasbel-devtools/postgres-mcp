# opencode V2 docs — MCP + config reference (student-config grounding)

Fetch date: 2026-11-23
Scope: plan step 1.4 (fetch half). Scratch only — a later step promotes to `{wt}/docs/reference/`.

## 1. Local-stdio server schema

Source: https://opencode.ai/docs/mcp-servers
SHA-256 of fetched page (raw HTML via `curl -sL`, 2026-11-23): `451915ebff99f1fb27c1207ad930553adef3948c2c165e791a6188ff55104e64`

### 1a. Hand-config verbatim (`mcp.servers.<name>`)

> "To configure a server by hand, give it a unique name under `mcp.servers`. V2 does not place server names directly under `mcp."
>
> ```jsonc title="opencode.jsonc"
> {
>   "$schema": "https://opencode.ai/config.json",
>   "mcp": {
>     "servers": {
>       "my-server": {
>         "type": "local",
>         "command": ["npx", "-y", "example-mcp-server"],
>       },
>     },
>   },
> }
> ```

### 1b. Local server full config verbatim

> "A local server is a command that OpenCode starts over the MCP stdio transport."
>
> ```jsonc title="opencode.jsonc"
> {
>   "$schema": "https://opencode.ai/config.json",
>   "mcp": {
>     "servers": {
>       "everything": {
>         "type": "local",
>         "command": ["npx", "-y", "@modelcontextprotocol/server-everything"],
>         "cwd": ".",
>         "environment": {
>           "LOG_LEVEL": "info",
>           "MCP_API_KEY": "{env:MCP_API_KEY}",
>         },
>       },
>     },
>   },
> }
> ```

### 1c. Local field table verbatim

| Field | Required | Description |
| --- | --- | --- |
| `type` | Yes | Must be `"local"`. |
| `command` | Yes | Executable followed by its arguments. |
| `cwd` | No | Process directory. Relative paths resolve from the workspace, which is also the default. |
| `environment` | No | String variables added to OpenCode's inherited process environment. |
| `disabled` | No | Prevents connection when `true`. Defaults to `false`. |
| `codemode` | No | Set to `false` to expose tools directly instead of through Code Mode. Defaults to `true`. |
| `timeout` | No | Per-server timeout overrides. |
| `protocol` | No | `legacy` (default), `auto`, or `2026-07-28`. |
| `pool` | No | Share one connection across directories. Defaults to `false`. |

### 1d. `{env:…}` substitution verbatim

> "Use `{env:NAME}` for environment substitution. Shell expressions such as `$NAME` are not expanded in JSON strings:"
>
> ```jsonc
> {
>   "environment": {
>     "MCP_API_KEY": "{env:MCP_API_KEY}",
>   },
> }
> ```

NOT COVERED by the local-stdio schema (do not guess): no `args` / `env` split — V2 local entries use a single `command` array plus an `environment` map. Any student-guide draft using `args` or `env` key names must be revised to `command` + `environment`. No `url`/`headers`/`oauth` on a local entry (those are remote-only fields on the same page).

## 2. `opencode mcp add` form (local command)

Source: https://opencode.ai/docs/mcp-servers (same SHA-256 as §1)

Verbatim:

> "Add one with a command after `--`:"
>
> ```sh
> opencode mcp add everything -- npx -y @modelcontextprotocol/server-everything
> ```
>
> "Pass environment variables with repeated `--env` flags:"
>
> ```sh
> opencode mcp add everything --env LOG_LEVEL=info -- npx -y @modelcontextprotocol/server-everything
> ```

Remote-only form (for contrast, NOT for the postgres local step):

```sh
opencode mcp add context7 --url https://mcp.context7.com/mcp
opencode mcp add context7 --global --url https://mcp.context7.com/mcp
```

Global flag: "Add `--global` to make it available in every project". Connection check: `opencode mcp list`. Auth flow: `/mcps` in OpenCode, `opencode mcp auth <name>`, `opencode mcp logout <name>`.

## 3. `providers` shape

Source: https://opencode.ai/docs/config
SHA-256 of fetched page (raw HTML via `curl -sL`, 2026-11-23): `e6b573732c1cfd9464f5d3aef6d21e868d49f4604e1746bff78e1a50c8d512e0`
Extended field reference: https://opencode.ai/docs/providers
SHA-256 of fetched page (raw HTML via `curl -sL`, 2026-11-23): `9fbb1bfed901f12b6e907d770762669b9d7aa5c78ff26a33d449966e3d13c169`

### 3a. `/docs/config` verbatim (providers entry point)

> "Configure providers and add or override their models, request settings, headers, and model variants."
>
> ```jsonc
> {
>   "providers": {
>     "openai": {
>       "models": {
>         "gpt-6.1-sol-custom": {
>           "modelID": "gpt-6.1-sol",
>           "name": "GPT-6.1 Sol Custom",
>           "limit": {
>             "context": 200000,
>             "output": 32000,
>           },
>         },
>       },
>     },
>   },
> }
> ```
>
> "Provider `settings.transport: "websocket"` selects its session WebSocket."
>
> "See the [providers guide](/providers) for credentials, custom endpoints, provider packages, the WebSocket transport, and model configuration."

### 3b. `/docs/providers` verbatim — custom provider shape

```jsonc title="opencode.jsonc"
{
  "$schema": "https://opencode.ai/config.json",
  "providers": {
    "acme": {
      "name": "Acme",
      "env": ["ACME_API_KEY"],
      "package": "@opencode/ai/providers/openai-compatible",
      "settings": {
        "baseURL": "https://llm.acme.example/v1",
      },
      "models": {
        "qwen3-coder": {
          "name": "Qwen 3 Coder",
        },
      },
    },
  },
}
```

> "The `providers` object is keyed by the provider ID used in model references, such as `acme/qwen3-coder`."

| Field | Purpose (verbatim) |
| --- | --- |
| `name` | Display name. |
| `env` | Ordered environment variable names that can provide the credential. |
| `package` | Runtime provider package. |
| `canonical` | Built-in provider ID whose catalog defaults this provider inherits. |
| `compatibility` | API quirks shared by every model of this provider. |
| `settings` | Typed OpenCode controls and JSON options passed to the runtime package. |
| `headers` | String-valued HTTP headers added to requests. |
| `body` | JSON fields merged into request bodies. |
| `models` | Models to add or override, keyed by the OpenCode model ID. |

Model map key rule (verbatim): "The map key is the model ID used by OpenCode; `modelID` changes the ID sent to the provider."

Variable substitution for secrets (from `/docs/config`, verbatim): `"model": "{env:OPENCODE_MODEL}"`, `"apiKey": "{env:ANTHROPIC_API_KEY}"` — "If the environment variable is not set, it will be replaced with an empty string."

UNVERIFIED for the student guide: which provider/model the course will pin (e.g. whether the lab uses a catalog provider vs. a custom gateway) is NOT in these docs excerpts — the student guide must not guess it; that choice belongs to a later plan step.

## 4. `permissions` shape (student guide dependency)

Source: https://opencode.ai/docs/permissions
SHA-256 of fetched page (raw HTML via `curl -sL`, 2026-11-23): `0c3bb0b2566dd494424247f8aa5b6bbc05d9fb85915961c3df42b6170a8fffc3`
Also summarized at https://opencode.ai/docs/config (same SHA-256 as §3).

Verbatim rule shape:

```jsonc
{
  "permissions": [
    { "action": "shell", "resource": "*", "effect": "ask" },
    { "action": "shell", "resource": "git status *", "effect": "allow" },
    { "action": "shell", "resource": "git diff *", "effect": "allow" },
    { "action": "shell", "resource": "git push *", "effect": "deny" },
  ],
}
```

> "Each rule requires three string fields:" `action` (tool permission action), `resource` (value being used), `effect` (`allow`, `deny`, or `ask`). "The last matching rule wins" / "OpenCode combines rules in order and uses the last match." "If no rule matches, OpenCode uses `ask`."

MCP-tool permission verbatim (from `/docs/mcp-servers`): "Use permission actions to hide or deny tools without disconnecting their server. Match the normalized `<server>_<tool>` name:"

```jsonc
{
  "permissions": [
    {
      "action": "context7_*",
      "resource": "*",
      "effect": "deny",
    },
  ],
}
```

UNVERIFIED: the exact `<server>_<tool>` names for the course postgres server are NOT in the opencode docs (they come from the postgres MCP server's own tool list) — the student guide must list them only after connecting the server and running `opencode mcp list` / inspecting the tool catalog, never by guessing.

## 5. Discovery

- https://opencode.ai/docs/llms.txt was fetched 2026-11-23; it is an index page (sections: Docs / Configure / CLI / Build / API / Console) linking to each guide above. No additional schema beyond §§1–4 was needed from it.
- Complete schema source of truth (per `/docs/config` verbatim): "The complete OpenCode configuration schema is available at opencode.ai/config.json." Student guide should cite `"$schema": "https://opencode.ai/config.json"` for editor validation.

## Verdicts for downstream steps

- stdio schema: VERIFIED — exact local entry shape is `mcp.servers.<name> = { type: "local", command: [...], cwd?, environment?, disabled?, codemode?, timeout?, protocol?, pool? }` with `{env:NAME}` substitution inside `environment`.
- `mcp add` local form: VERIFIED — `opencode mcp add <name> [--env K=V ...] -- <command...>`; `--global` for machine-wide.
- `providers` shape: VERIFIED as the generic map shape above; the course's concrete provider choice is UNVERIFIED (later step decides).
- `permissions` shape: VERIFIED as the `{action, resource, effect}` ordered-rules shape; exact postgres tool-name rules are UNVERIFIED until the server's tool catalog is observed.
