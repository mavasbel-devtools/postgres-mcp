# Free model endpoints for the postgres-mcp lab

Date: 2026-11-24. Purpose: no-cost inference endpoints a student can use for the
lab, with the opencode provider id and sign-in command for each. No API keys or
tokens are recorded in this note.

How hashes were produced: `curl -sL --max-time 40 <URL> -o <file>` then
`shasum -a 256 <file>`, fetch date from `date -u +%Y-%m-%d` (2026-11-24).
`webfetch` was used only to read rendered pages; every hash below is over the
`curl`-saved bytes.

## 1. Candidate endpoints

| Candidate | Signup URL | Free limits (quoted from live page) | Page SHA-256 (curl bytes) | Card / phone required? | opencode provider id | Student sign-in |
|---|---|---|---|---|---|---|
| OpenRouter (`:free` models) | https://openrouter.ai (account via site header) | "Free usage limits: If you're using a free model variant (with an ID ending in `:free`), the following limits apply:" — Credits purchased (all time) / Requests per minute / Requests per day: "Less than 10" credits → 20 RPM / 50 RPD; "At least 10" → 20 RPM / 1000 RPD. Page JS constants confirm: `FREE_MODEL_RATE_LIMIT_RPM=20`, `FREE_MODEL_NO_CREDITS_RPD=50`, `FREE_MODEL_HAS_CREDITS_RPD=1000`, `FREE_MODEL_CREDITS_THRESHOLD=10`. Per-key counters via `GET /api/v1/key` → `free_model_daily_requests { used, limit, remaining }`. Source: https://openrouter.ai/docs/api-reference/limits | `46250ff8644b75abdd196c46b8ae894a52101d95e0917aee8a140097941afc04` | No card/phone for `:free` use; buying credits (which only raises the daily cap 50 → 1000) requires payment. Signup is email/Google/GitHub OAuth — confirm the current options at signup time. | `openrouter` (native runtime; `model: "openrouter/<openrouter-model-id>"`, e.g. `openrouter/anthropic/claude-sonnet-5.5` per https://opencode.ai/docs/providers) | `opencode auth login` (target: the `openrouter` integration), or `/connect` in the TUI then `/models` |
| Google AI Studio (Gemini Developer API, Free tier) | https://aistudio.google.com ("Get started for Free" button on the pricing page; paid upgrade is the separate https://aistudio.google.com/api-keys flow) | Free card: "Limited access to certain models", "Free input & output tokens", "Google AI Studio access", "Content used to improve our products". Example model row — Gemini 2.5 Flash, Standard tab: "Input price: Free of charge", "Output price (including thinking tokens): Free of charge", "Grounding with Google Search: Free of charge, up to 500 RPD (limit shared with Flash-Lite RPD)". Note: 2.5 Flash "is deprecated and is no longer available to select in Google AI Studio. Effective December 1, 2026, all API requests to `gemini-2.5-flash` will automatically route to Gemini 3.5 Flash-Lite". Per-model interactive RPM/RPD/TPM "depend on a variety of factors (such as your usage tier) and can be viewed in Google AI Studio". Source: https://ai.google.dev/pricing (rate-limits detail: https://ai.google.dev/gemini-api/docs/rate-limits) | pricing page `3d7b87d69e839c4b969a0d953ff29f4b8f4ce5e5771f37fb95beb01459c2cfcc`; rate-limits page `curl` bytes saved 2026-11-24 (see gate log) | Free tier needs a Google account only; a payment method enters only via the paid-upgrade flow. No phone number is requested by the free flow on the pages fetched. | `google` (opencode console catalog lists Google among built-in providers, https://opencode.ai/docs/console/providers; confirm exact id in the `/connect` picker) | `opencode auth login`, or `/connect` in the TUI then `/models` |
| Groq (GroqCloud Free tier) | https://console.groq.com (site "Start building" links to https://console.groq.com/home; keys at https://console.groq.com/keys per https://console.groq.com/docs/coding-with-groq/opencode) | Rate-limits page has a "Free Plan Limits – Developer Plan Limits" toggle; "the limits shown below are the base limits for the Developer plan", and "you can view the current, exact rate limits for your organization on the limits page in your account settings" (https://console.groq.com/settings/limits). Example row shown: `openai/gpt-oss-120b` — 30 RPM / 1K RPD / 8K TPM / 200K TPD. Usage is metered in RPM / RPD / TPM / TPD (/ ASH / ASD for audio). Tool use is a documented core feature (docs nav: Tool Use, local tool calling, MCP). Sources: https://console.groq.com/docs/rate-limits, https://console.groq.com/docs/billing-faqs | rate-limits `76e17316fee91b0a10da0c5ae2706115959b86ef56f70f295ddce88650632a08`; billing-faqs `6f70d7d7504288747c6685a1834e33f894da5e367f2e7b28f960fd831502e89c` | No: "To upgrade from the Free tier to the Developer tier, you'll need to provide a valid payment method" — i.e. the Free tier requires none. | `groq` (console catalog lists Groq; docs: "Run `/connect`, search for Groq … enter your Groq API key … Run `/models`") | `opencode auth login`, or `/connect` in the TUI then `/models` |
| Cerebras — DISQUALIFIED as a no-cost endpoint | https://cloud.cerebras.ai | "Is there a permanently free tier? No. The Free Trial is time- and credit-bounded: $5 in credits that expire 30 days after they're granted." "If you skip adding a payment method at sign-up, Playground and API access remain inactive until you do." "There is no charge until you choose to purchase additional credits." Free Trial caps (while the $5 lasts), e.g. `gpt-oss-120b`: 5 RPM / 30K uncached TPM / 90K total TPM / 1M TPH / 1M TPD; `qwen-3.8-27b`: 300 RPM / 150K uncached TPM / 750K total TPM. Source: https://inference-docs.cerebras.ai/rate-limits (pricing footnotes: https://www.cerebras.ai/pricing) | rate-limits `ebc0405cee8997a15143147103471ae61e8af32e76c61c142c3e62a76bf0ba86`; pricing `505e19b423996001b1574333984ba3f609c4efd4b6f6bc015e80d36d6ec2be3e6` | YES — verified payment method required at signup; trial expires. Not usable for a no-card lab. | `cerebras` (for reference only; still needs a paid-verified account) | n/a for this lab |

Successor / related path found during search: OpenRouter's Free Models Router
(`openrouter/free`) "automatically selects a free model at random … The router
intelligently filters for models that support the features your request needs,
such as image understanding, tool calling, and structured outputs."
Source: https://openrouter.ai/docs/cookbook/get-started/free-models-router-playground.md,
SHA-256 `877355ccc60e5c85d75b487ec1029eb45fc52d206420de14c13fc20f769aa7c6`
(useful as a fallback, but pinned model ids below are preferred for
reproducibility). Cerebras itself points at partner gateways (AWS Marketplace,
OpenRouter, Hugging Face, Vercel) rather than offering its own free tier.

## 2. OpenRouter `:free` models with tool support (2026-11-24)

Source: https://openrouter.ai/api/v1/models, fetched with
`curl -sL https://openrouter.ai/api/v1/models -o or-models.json`,
SHA-256 `39ae34f962a2045d57c2f3a71d6b37da65e032d2077cb2b4ef8e813c546266d9`,
473 models total, 12 `:free`. Every one lists `tools` in
`supported_parameters` (exact arrays quoted from the fetched JSON):

- `inclusionai/ling-3.2-flash:free` — `[…, "tool_choice", "tools", "top_k", "top_p"]`
- `baidu/ernie-5.5-flash-preview:free` — `[…, "tool_choice", "tools", "top_p"]`
- `liquid/lfm-3-1.7b:free` — `[…, "tool_choice", "tools", "top_k", "top_logprobs", "top_p"]`
- `particle-ai/particle-1:free` — `[…, "tool_choice", "tools", "top_k", "top_logprobs", "top_p"]`
- `recursive/flint-v1.0:free` — `[…, "temperature", "tools", "top_logprobs", "top_p"]`
- `nvidia/nemotron-3.5-super-vl:free` — `[…, "tool_choice", "tools", "top_p"]`
- `dots-studio/dots-3-note-preview:free` — `[…, "tool_choice", "tools", "top_p"]`
- `nvidia/nemotron-3.5-lightning:free` — `[…, "tool_choice", "tools", "top_p"]`
- `nvidia/nemotron-3-ultra-550b-a55b:free` — `[…, "tool_choice", "tools", "top_p"]`
- `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` — `[…, "tool_choice", "tools", "top_p"]`
- `google/gemma-4-26b-a4b-it:free` — `[…, "tool_choice", "tools", "top_p"]`
- `google/gemma-4-31b-it:free` — `[…, "tool_choice", "tools", "top_p"]`

Cross-check against the proxy (read-only; repo at
the accounts-proxy checkout itself,
not modified, no tokens printed): `bun run proxy models openrouter` (exit 0) routes all 12 of the 12
ids above (`… | grep -c ':free'` → `12`), e.g.
`openrouter/nvidia/nemotron-3.5-lightning:free … context 1000000 / output 65536`.

## 3. Recommendation (tool calling is mandatory — all picks have `tools`)

- Default: `openrouter/nvidia/nemotron-3.5-lightning:free`
  (opencode model id `openrouter/nvidia/nemotron-3.5-lightning:free`).
  Why: `tools` in `supported_parameters` (quoted above); independently proven
  for agentic use — accounts-proxy live results
  (`docs/reference/2026-10-18-20-07-p6-live-results.md`) show
  `openrouter/nvidia/nemotron-3.5-lightning:free` 4/4 passing on all three
  protocols (openrouter-chat, openrouter-msg, openrouter-resp); 1M context.
- Fallback 1: `openrouter/google/gemma-4-31b-it:free`.
  Why: `tools` in `supported_parameters`; Gemma family from the same vendor as
  the AI Studio path, so behavior is comparable across the two free routes;
  262144 context.
- Fallback 2: `openrouter/baidu/ernie-5.5-flash-preview:free`.
  Why: `tools` in `supported_parameters`; already exercised as the live-test
  model in accounts-proxy (`pi-openrouter` test targets
  `ap-openrouter/openrouter/baidu/ernie-5.5-flash-preview:free`); 1024000 context.

No candidate failed the tool-support gate: all 12 `:free` models include
`tools`, so no escalation was needed.

## 4. Gate evidence (commands + output)

- `curl -sL https://openrouter.ai/api/v1/models -o or-models.json` → 918083 bytes;
  `date -u +%Y-%m-%d` → `2026-11-24`;
  `shasum -a 256 or-models.json` → `39ae34f9…793c546266d9` (full in §1/§2).
  473 models, 12 `:free`, each with `tools` in `supported_parameters` (arrays
  quoted in §2).
- `(inside the accounts-proxy checkout) bun run proxy models openrouter`
  → exit 0, 473 models; `grep -c ':free'` → `12`, ids identical to the 12 above.
- `curl -sL --max-time 40 <page> -o <file>` + `shasum -a 256` for every page in
  §1 (full digests in the table), all fetched 2026-11-24; webfetch used only for
  reading, never for hashes.
- `opencode auth login --help` → `DESCRIPTION: connect an integration / USAGE:
  opencode auth login [flags] [<target>]` — the student sign-in command exists.
- Gaps reported, not filled: (a) OpenRouter's exact signup-page URL and
  OAuth options were not fetched — confirm at lab time; (b) Groq's static page
  shows Developer-plan base limits with a plan toggle, so exact Free-plan
  numbers must be read from the student's own https://console.groq.com/settings/limits;
  (c) Cerebras has no permanently free tier (payment method required), so it is
  recorded but disqualified.
