# 🛡️ Revive — AI Revenue Recovery for Razorpay merchants

**Razorpay AI Buildathon · Track 03 (AI Revenue Recovery)** · by Pari Singhal

[![CI](https://github.com/parisinghal31/Revive-Revenue-Recovery-Tool/actions/workflows/ci.yml/badge.svg)](https://github.com/parisinghal31/Revive-Revenue-Recovery-Tool/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-black?style=flat-square)](LICENSE)
![API keys needed to verify every claim: zero](https://img.shields.io/badge/API%20keys%20to%20verify-zero-2ea44f?style=flat-square)
![Deterministic](https://img.shields.io/badge/headline%20%E2%82%B9-reproducible%20to%20the%20rupee-2ea44f?style=flat-square)

[![Watch the Revive demo, 5 minutes](https://i.vimeocdn.com/filter/overlay?src0=https%3A%2F%2Fi.vimeocdn.com%2Fvideo%2F2197326592-ebedce84fad2ec338dcb38aaf4f201dd4f179048f2dec1650af903252a4fe3e0-d_1280x720%3Fregion%3Dus&src1=http%3A%2F%2Ff.vimeocdn.com%2Fp%2Fimages%2Fcrawler_play.png)](https://vimeo.com/1223978353)

*[Watch the demo on Vimeo](https://vimeo.com/1223978353) (5:35).*

Razorpay's native retry is time-based (T+1/T+2/T+3), regardless of **why** a payment failed. Retrying an expired card tomorrow is always wasted; calling a hesitant customer works. **Revive diagnoses the decline code first**, picks a bounded intervention (Hinglish voice call, WhatsApp UPI link, smart-timed retry, bank-outage hold, subscription save), runs it through five server-side guardrails, and measures the rupees it brings back. Every decision, check, and action is written to an audit trail *before* it executes.

```
payment.failed ──► DECISION LAYER ──► GUARDRAILS ──► BOUNDED ACTION ──► ₹ RECOVERED
  (webhook)        decline code →      5 checks,      voice / WhatsApp /   live counters,
                   root cause →        audited BEFORE  retry / hold /      audited, and
                   intervention        any action      mandate-save        reproducible
```

## Judged on four things — here's each one, and where to check it

| Criterion | The one-line answer | Verify |
|---|---|---|
| **Problem taste** | Razorpay's native retry is time-based (T+1/T+2/T+3) and throws away the only signal that matters: **why** the payment failed. Retrying an expired card tomorrow is arithmetic, not recovery. Revive routes on the decline code. | [The decision layer](#the-decision-layer-llm-proposes-rules-dispose) |
| **Build quality** | 20 tests, green CI on every push, a headline number that reproduces to the rupee with **zero API keys**, a `/health` probe, and a one-click deploy blueprint. | [Verify in five minutes](#verify-this-repo-in-five-minutes-for-reviewers) |
| **AI judgment** | "LLM proposes, rules dispose" — a bounded 5-action menu with a validator that rejects off-menu answers, **plus five places we deliberately refused to use a model**. | [Where we did *not* use AI](#where-we-deliberately-did-not-use-ai) |
| **Failure recovery** | Both kinds: what the **system** does when a dependency dies, and what **we** did when the build broke — nine real incidents with root causes. | [What broke](#what-broke-and-what-we-did-about-it) |

## Measured on a batch, not a demo

One command, **zero API keys**, fresh isolated database, deterministic seed:

```bash
cd backend && pip install -r requirements.txt && python demo.py
```

| Metric | Value (n=500, seed=42) |
|---|---|
| ₹ at risk | **₹19,41,916** |
| ₹ recovered | **₹9,60,695** (250 payments) |
| Recovery yield | **50.0%** |
| Fraud suppressed | 2 cases — ₹200 **deliberately not chased** (card-testing pattern) |
| Outage handling | 18 HDFC retries **held during the outage**, released as a batch on recovery |
| Honest losses | **244 cases (₹9,70,867) — reported, not hidden** |

The committed [`results/batch_report.json`](results/batch_report.json) was produced by exactly this command. Re-run it: the numbers reproduce to the rupee (`tests/test_batch.py::test_batch_is_reproducible_for_a_fixed_seed` proves it in CI). A batch with zero losses would be cherry-picked; this one resolves each intervention at honest, decline-code-dependent success rates.

## Verify this repo in five minutes (for reviewers)

```bash
# 1. Guardrails, engine routing, LLM-boundary, batch honesty, health probe — 20 tests
cd backend && pip install -r requirements-dev.txt && python -m pytest tests -q

# 2. The headline numbers, reproducibly, keyless
python demo.py --n 500 --seed 42

# 3. The full product (still keyless — simulated gateway + policy table)
uvicorn app.main:app --port 8000          # backend
cd ../frontend && npm install && npm run dev   # storefront http://localhost:3000
# open /dashboard, buy something at /, fail the payment, watch the audit trail
```

Everything degrades gracefully without keys: no LLM key → deterministic policy table (audited as such); no Razorpay key → simulated card picker; no Vapi/WhatsApp keys → decisions and audit rows still flow. CI (`.github/workflows/ci.yml`) runs the tests and the reproducible batch on every push.

## Tools & tech stack

Every choice below is either free-tier or self-hosted, and each one is load-bearing.

| Layer | Stack | Why this one |
|---|---|---|
| **Frontend** | ![Next.js](https://img.shields.io/badge/Next.js%2016-000000?style=for-the-badge&logo=nextdotjs&logoColor=white) ![React](https://img.shields.io/badge/React%2019-20232A?style=for-the-badge&logo=react&logoColor=61DAFB) ![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white) | App Router gives server-rendered recovery pages that open instantly from a WhatsApp link on a cold phone browser. |
| **Styling & motion** | ![Tailwind CSS](https://img.shields.io/badge/Tailwind%20v4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white) ![Framer Motion](https://img.shields.io/badge/Framer%20Motion-0055FF?style=for-the-badge&logo=framer&logoColor=white) ![Lucide](https://img.shields.io/badge/Lucide-F56565?style=for-the-badge&logo=lucide&logoColor=white) | A merchant dashboard is watched for hours; motion carries state changes without a page refresh. |
| **Backend** | ![Python](https://img.shields.io/badge/Python%203.11-3776AB?style=for-the-badge&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white) ![Uvicorn](https://img.shields.io/badge/Uvicorn-2F9E44?style=for-the-badge) | Async web framework with native WebSockets — the audit trail streams live to the dashboard on the same process. |
| **Storage** | ![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white) | One file, zero external services, trivially isolatable per test and per batch (`REVIVE_DB_PATH`). The audit trail is the product; a heavyweight DB would add ops burden without adding truth. |
| **Decision LLM** | ![Groq](https://img.shields.io/badge/Groq-F55036?style=for-the-badge) ![Gemini](https://img.shields.io/badge/Gemini-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white) | `groq/gpt-oss-120b` for sub-second routing decisions; `gemini-2.0-flash` as a drop-in alternate. Both free-tier, both behind one OpenAI-compatible call. |
| **Voice** | ![Vapi](https://img.shields.io/badge/Vapi-12A594?style=for-the-badge) ![OpenAI](https://img.shields.io/badge/GPT--4o--mini-412991?style=for-the-badge) ![Deepgram](https://img.shields.io/badge/Deepgram%20nova--2-13EF93?style=for-the-badge&logo=deepgram&logoColor=black) | Vapi orchestrates the call and calls **our** tools server-side; `Naina` voice + Hindi transcription make Hinglish actually land. |
| **Payments** | ![Razorpay](https://img.shields.io/badge/Razorpay-0C2451?style=for-the-badge&logo=razorpay&logoColor=white) | Real test-mode Orders, Checkout, webhooks with HMAC verification, and order-payments reconciliation. |
| **Messaging** | ![WhatsApp](https://img.shields.io/badge/WhatsApp%20Cloud%20API-25D366?style=for-the-badge&logo=whatsapp&logoColor=white) ![Twilio](https://img.shields.io/badge/Twilio-F22F46?style=for-the-badge&logo=twilio&logoColor=white) | A provider chain, not a dependency — see [what broke](#what-broke-and-what-we-did-about-it). |
| **Delivery** | ![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white) ![Render](https://img.shields.io/badge/Render-46E3B7?style=for-the-badge&logo=render&logoColor=black) ![Vercel](https://img.shields.io/badge/Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white) | CI runs the tests *and* the reproducible batch on every push; `render.yaml` deploys the backend with no secrets in the repo. |

## Architecture

```mermaid
flowchart LR
    subgraph Storefront ["Tomato storefront (Next.js)"]
        CO[Checkout<br/>real Razorpay test-mode modal]
        PAY["/pay/:id recovery page<br/>real order at negotiated price"]
        GOLD["/gold subscription<br/>UPI autopay mandate"]
        CALL["/call/:id in-browser call<br/>@vapi-ai/web (WebRTC)"]
    end

    subgraph Backend ["Revive backend (FastAPI + SQLite)"]
        WH["/webhook/razorpay<br/>real + simulated shapes, HMAC verify"]
        ENG[Decision engine<br/>decline code → root cause → intervention]
        LLM["LLM reasoning layer<br/>groq/gpt-oss-120b — proposes only"]
        GR[Guardrail layer<br/>5 checks, each audited]
        AUD[(Audit log +<br/>failures/actions/recoveries)]
        WS[WebSocket hub]
    end

    subgraph Channels
        VAPI[Vapi voice agent 'Asha'<br/>Hinglish, tool-calling, Naina voice]
        WA[WhatsApp providers<br/>Meta Cloud API / Twilio template]
    end

    DASH[Merchant dashboard<br/>counters · brain · transcript · audit · bank health]

    CO -->|payment.failed| WH --> ENG
    GOLD -->|subscription.cancelled| WH
    ENG <--> LLM
    ENG --> GR --> AUD
    GR --> VAPI & WA
    VAPI -->|"tool calls (server-side)"| GR
    WA --> PAY -->|paid| WH
    AUD --> WS --> DASH
    CALL <--> VAPI
```

**Component map**

| Piece | File | What it does |
|---|---|---|
| Webhook ingress | `backend/app/main.py` | Accepts real Razorpay `payment.failed` (`payload.payment.entity` + `X-Razorpay-Signature` HMAC-SHA256) and simulated flat events on one endpoint; reload-safe order reconciliation via Razorpay's order-payments API |
| Decision engine | `backend/app/engine.py` | Decline code → root cause → intervention; fraud check first on every failure; bank hold/release; recovery recording (idempotent, discount-aware) |
| LLM layer | `backend/app/llm.py` | "LLM proposes, rules dispose" (details below) |
| Guardrails | `backend/app/guardrails.py` | The five checks — every pass AND every block writes an audit row |
| Voice agent | `backend/app/voice.py` | Transient Vapi assistant built per call: Hinglish persona, 5 server-guarded tools, live transcripts + intent chips, bounded call duration, auto-hangup |
| WhatsApp | `backend/app/whatsapp.py` | Provider chain with the production template path documented in-file |
| Razorpay gateway | `backend/app/razorpay_gw.py` | Orders API, webhook signature verification, error-taxonomy → decline-code mapping (tested) |
| Batch simulator | `backend/app/simulator.py` | The measurement harness (methodology below) |
| Persistence | `backend/app/db.py` | SQLite, single file, zero external services; `REVIVE_DB_PATH` for isolation |
| Dashboard | `frontend/src/app/dashboard/` | Live command center: cumulative-recovery chart, yield-vs-target, KPI row, agent brain, transcript with intent chips, audit stream, bank-health strip with one-click recovery release |

## The decision layer: LLM proposes, rules dispose

Two decision paths, both audited with which one decided:

1. **Live traffic.** The LLM (Groq `gpt-oss-120b`, or Gemini, via OpenAI-compatible endpoints) receives the failure context: decline code, amount, method, bank health, IST hour, and the customer's recent failure velocity. It must return JSON choosing **one of five menu actions** with a root cause, reasoning, and confidence. The reasoning streams to the dashboard's Agent Brain panel tagged with the model name.
2. **Batch runs and keyless mode.** The deterministic policy table (`engine.py:DECISION_TABLE`) decides. Batches always use it, for reproducibility and honest measurement; the batch's first audit row discloses this.

The LLM's authority is deliberately narrow:

- **Off-menu proposals are rejected** by a validator and the table takes over, with an audit row saying so (`tests/test_engine.py::test_out_of_menu_llm_proposal_is_rejected`). Bounded actions mean bounded *even for the model*.
- It never sets amounts, touches money, or bypasses a guardrail. Every action it picks still passes all five checks.
- Domain priors are explicit in the prompt (OTP abandonment = hesitation → call converts best; card problems → UPI pivot; gateway noise → silent retry), and the model may deviate only with a concrete stated reason, which produces genuinely non-hardcoded behavior: a ₹159 order gets a WhatsApp link ("a call is intrusive for this amount"), a ₹1,500 one gets a call, and at 11 PM it reasons about not waking the customer.

| Decline code | Root cause | Intervention |
|---|---|---|
| `AUTHENTICATION_FAILED` | OTP/3DS abandoned — hesitation | Hinglish voice call, bounded negotiation |
| `CHECKOUT_ABANDONED` | Price hesitation | Voice call, ≤10% discount authority |
| `CARD_EXPIRED` | Retry is always wasted | WhatsApp link → pay by UPI instead |
| `PAYMENT_DECLINED` / `TXN_LIMIT_EXCEEDED` | Issuer/limit | WhatsApp link, alternate method |
| `INSUFFICIENT_FUNDS` | No balance ≠ no intent | Retry scheduled for the 1st (salary day) |
| `GATEWAY_ERROR` / `SERVER_ERROR` | Transient | Silent retry T+30min — customer never bothered |
| `ISSUER_DOWN` | Bank outage | **Hold ALL retries for that bank**; release as a batch on recovery, then send UPI links |
| `MANDATE_CANCELLED` | Subscription churn | Save-outreach with pause→downgrade ladder + autopay restart link → MRR saved |

## Where we deliberately did *not* use AI

Five places where a model was the obvious move and the wrong one:

| Where | What we used instead | Why a model would be worse |
|---|---|---|
| **The five guardrails** | Plain Python `if` statements (`guardrails.py`) | A control you can argue with is not a control. The discount ceiling is `if discount > 0.10: block` — no prompt, jailbreak, or persuasive customer negotiates with an if-statement. Every check is unit-tested; a model's would be sampled. |
| **The measurement path** | The deterministic policy table (`engine.py:DECISION_TABLE`) | Put an LLM in the batch and the headline ₹ stops being reproducible — and an unfalsifiable number is worth nothing to a judge. Batches disclose in their first audit row that the table decided. |
| **Decline code → root cause** | A lookup table | It is a **finite, documented, unambiguous** taxonomy. Asking a model to re-derive `CARD_EXPIRED → retry is wasted` on every request buys latency, cost, and variance in exchange for zero information. |
| **Fraud detection** | A counter and a 60-second window | "≥5 failures from one source in 60s" is not a judgment call. A classifier here would add false positives to a decision that *suppresses revenue* — the one place we least want creativity. |
| **Anything touching an amount** | Order data + a fixed ladder | The LLM picks one of five actions. It never sets a price, a discount, or a refund. Money is arithmetic on stored values, not generation. |

The model earns its place reading a messy, context-heavy situation (decline code + amount + hour + bank health + this customer's recent failure velocity), choosing among bounded options, and explaining itself in a sentence a merchant can read. A validator still checks the result before anything happens.

## Guardrails — stopping rules and compliant escalation

Every check runs **before** the action and writes an audit row whether it passes or blocks (`backend/app/guardrails.py`, each verified in `tests/test_guardrails.py`):

| # | Guardrail | Rule | On trip |
|---|---|---|---|
| 1 | **TRAI quiet hours** | No outbound calls 9 PM–9 AM IST (window editable from the dashboard sandbox) | Action **QUEUED** until the window ends, never placed |
| 2 | **Opt-out blacklist** | "call mat karo" → permanent | All contact **HALTED**, across all future failures |
| 3 | **Discount ceiling** | 10% hard cap, checked server-side | Tool call **BLOCKED** — the voice agent cannot exceed it no matter what it says |
| 4 | **Contact budget** | Max 1 outbound contact per failure | Re-contact **BLOCKED** (no spam) |
| 5 | **Fraud velocity** | ≥5 failures/60s from one source | Recovery **SUPPRESSED** — an agent that knows when *not* to recover money |

Plus bounded calls (15s silence timeout, 5-minute hard cap) and a batch-mode kill switch that suppresses all external sends during simulations (`tests/test_batch.py::test_batch_never_sends_external_messages`).

## The voice agent

"Asha" is a transient Vapi assistant built per call (`voice.py:build_vapi_assistant`), with no dashboard config and full reproducibility from code. Hinglish persona (Vapi's `Naina` Indian voice, slightly slowed), Deepgram `hi` transcription, GPT-4o-mini conversation. Her five tools all execute **server-side through the guardrails**: `apply_discount` (ceiling-checked), `send_upi_link` (WhatsApp mid-call), `schedule_retry`, `opt_out` (instant blacklist + hang up), and `check_payment_status`, so when the customer pays the link mid-call and says "ho gaya", she verifies against the database before celebrating "payment mil gaya!". Final transcripts stream to the dashboard with LLM-classified intent chips (`PRICE_OBJECTION` / `OPT_OUT` / `NO_FUNDS` / `AGREEMENT`); she hangs up on her own when the conversation is done.

## Real Razorpay rails

- **Orders API:** every checkout and every recovery page creates a real test-mode order (recovery orders at the *negotiated* price, so the discount is visible in the Razorpay dashboard too).
- **Real Checkout:** `checkout.js` modal, `payment.failed` client events for sub-second UX, plus the server-verified webhook path.
- **Webhook signature verification:** HMAC-SHA256 against `RAZORPAY_WEBHOOK_SECRET`; unsigned webhooks are accepted but explicitly audited as unverified.
- **Reload-safe reconciliation:** if a redirect wipes the page mid-payment, the order is reconciled through Razorpay's order-payments API (dedup by `order_id`).
- **Error-taxonomy mapping:** Razorpay's `error_code/reason/description/step` are mapped to Revive's decline codes with substring-tolerant matching (`razorpay_gw.py:map_failure`, tested). Test mode only emits generic failure reasons, so the checkout offers a disclosed "treat this decline as X" overlay. The transport is real, the taxonomy is overlaid, and both are audited as such.

## Batch methodology (why the numbers are defensible)

`simulator.py` generates a failure stream with a decline-code distribution modeled on India payment-failure patterns (issuer/bank issues dominate, then customer drop-off, then gateway noise), then injects two adversities mid-batch: an **18-failure HDFC outage cluster** (the agent must hold, not hammer) and a **6-failure card-testing burst** (the agent must suppress, not chase). Recovery is only *attempted* where the engine chose an intervention, and succeeds at honest per-code probabilities (e.g., silent retries on transient gateway errors land ~80%; issuer declines only ~35%). Discounts on voice recoveries follow the negotiation ladder distribution (most calls need none). Everything is seeded, so the same seed gives the same rupees.

## Buildathon bar → where it's met

| Judging signal | Where |
|---|---|
| **Measured ₹ on a batch, not demos** | `demo.py` + committed `results/batch_report.json` + reproducibility test |
| **Audit trail** | Every decision/check/action writes a row *before* execution (`events.py:audit`); dashboard streams it live; `/api/audit` serves it |
| **Bounded, gated money actions** | 10% ceiling server-side; 5-action LLM menu with validator; voice tools have no direct money authority; recovery orders created only at guarded prices |
| **Stopping rules** | Opt-out blacklist, contact budget, fraud suppression, quiet-hours queueing, bank holds |
| **Compliant escalation** | TRAI quiet hours; consent-gated contact; opt-out is permanent and honored across failures |
| **Honest failure reporting** | 244 losses in the headline report; keyless fallbacks audited as such; workarounds disclosed in audit rows themselves |
| **Graceful failure handling** | Issuer outage → hold & batch-release; LLM timeout → policy table ("graceful degradation" audit row); WhatsApp/voice provider failures audited, flow continues |
| **Uses Razorpay rails** | Orders, Checkout, webhooks + signatures, order-payments reconciliation, error taxonomy, subscriptions story (mandate save → MRR) |

## What broke, and what we did about it

Nine real failures from this build, each with its root cause and the fix that shipped.

| # | What we saw | Root cause | What we did |
|---|---|---|---|
| 1 | Customer accepted a 10% discount on a live call and **every tool silently failed** | The cloudflared quick tunnel had died, so Vapi's cloud could not reach `/vapi/tools`. Tunnels died **three times** during the build. | Restarted and re-pointed `PUBLIC_URL` — then removed the failure class entirely by shipping `render.yaml`, so the backend gets a permanent URL instead of a disposable one. |
| 2 | Free Vapi number **refused to dial +91** | Free telephony blocks international dialling. | Probed the API until a free **SIP number** worked, then dialled SIP→SIP into a free Linphone account. The demo phone genuinely rings, at ₹0. Production is a one-line swap to a paid imported number. |
| 3 | Twilio WhatsApp returned **error 21654** | Sandbox senders are template-only and the 24-hour session had expired — a dead end, not a bug. | Stopped depending on any single provider: built a chain (Meta Cloud API → Green API → CallMeBot → Twilio) where the first configured one wins and every failure is audited. |
| 4 | A bridge offered instant WhatsApp delivery — **if we linked the owner's account by QR** | It worked. It also meant handing a third party a live WhatsApp session. | **Rejected it and deleted the provider**, despite it being the fastest path to a working demo. Account-takeover surface is not a demo shortcut. |
| 5 | The LLM sent a WhatsApp link for a **₹1,198 OTP abandonment**, where a call converts far better | The prompt stated the action menu but no **channel priors** — the model had no basis to prefer voice at higher amounts. | Added explicit priors (hesitation codes → call above ~₹500; card codes → link; gateway noise → silent retry) plus a rule that deviating requires a stated reason. Re-ran: 3/3 routed to `voice_call`. |
| 6 | Customer paid mid-call, said "ho gaya" — **Asha had no way to check** | The agent had five *write* tools and no *read* tool. | Added `check_payment_status`, plus a prompt rule to verify before celebrating. Both branches (paid / not yet) verified end-to-end. |
| 7 | Real calls **never streamed transcripts** | The transcript pipeline had only ever been wired to mock calls — a demo feature masquerading as a real one. | Wired Vapi `serverMessages` (transcript / status-update / tool-calls) into the real handler and **deleted the entire mock-call machinery** rather than leave two code paths. |
| 8 | CI's frontend type-check would have **failed on the very first push** | `layout.tsx` used `LayoutProps<"/">`, a type Next generates into the git-ignored `.next/`. A fresh CI checkout can never resolve it. | Replaced it with an explicit prop type. Caught **before** pushing, by running the type-check against a no-`.next` tree — exactly what CI sees. |
| 9 | `demo.py` crashed on Windows with `UnicodeEncodeError` on `₹` | Windows consoles default to cp1252. The docstring promised the run works "on any machine"; it did not. | Forced UTF-8 stdout. The claim and the code now agree. |

Most of these fixes remove the failure class rather than the symptom: a permanent URL instead of a restarted tunnel, a provider chain instead of one working provider, a deleted mock path instead of two code paths. Incident 4 went the expensive way and cost a working WhatsApp demo.

## Free-tier engineering (disclosed, with production paths in-code)

This was built entirely on free tiers as a student project. Each workaround is disclosed in the audit rows it writes, and the production path is documented as commented reference code beside it:

| Capability | Demo implementation | Production path (documented at) |
|---|---|---|
| Outbound phone ring | Vapi **SIP→SIP** call to a free Linphone account (free Vapi numbers can't dial +91 PSTN) | One-line change to a paid imported number — `voice.py`, "PRODUCTION PATH" block |
| WhatsApp delivery | Meta Cloud API test number / personal-use bridges | Verified WABA sender + approved Utility template — `whatsapp.py`, "PRODUCTION PATH" block |
| Decline variety | Disclosed scenario overlay on real test-mode events | Live mode emits real taxonomy; overlay layer deletes cleanly |
| Bank-recovery signal | Manual "bank up" control on the dashboard | Razorpay `payment.downtime.started/resolved` webhooks drive hold/release |
| UPI collect | Simulated approval on the recovery page when keyless; real test-mode modal when keyed | Same page; production account enables live UPI |

## Trust & anti-phishing design

An unsolicited payment link is structurally identical to a scam, so the design assumes suspicion: messages quote the exact order ID and amount seconds after the customer's own failed attempt; on calls the link is announced before it arrives; the link opens the merchant's own payment page where the customer initiates payment in their **own** UPI app (no OTP/PIN is ever requested, the opposite of the collect-request scam pattern); and paying from the app remains an alternative path. Production adds the verified-business sender badge.

## Repository layout

```
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI routes: webhook, checkout, voice, sandbox, dashboard APIs
│   │   ├── engine.py          # decision engine + bank holds + recovery recording
│   │   ├── llm.py             # bounded LLM proposals (Groq/Gemini) + intent classifier
│   │   ├── guardrails.py      # the five checks
│   │   ├── voice.py           # Vapi assistant, tools, transcripts, SIP calling
│   │   ├── whatsapp.py        # provider chain + production template path
│   │   ├── razorpay_gw.py     # Orders API, HMAC verify, error-taxonomy mapping
│   │   ├── simulator.py       # measurement harness
│   │   ├── db.py              # SQLite schema + helpers
│   │   └── events.py          # audit writer + WebSocket hub + metrics
│   ├── tests/                 # 20 tests: guardrails, routing, LLM boundary, batch honesty, health
│   ├── demo.py                # one-command reproducible proof run
│   ├── requirements.txt / requirements-dev.txt
│   └── start.example.ps1      # env template (no secrets in repo)
├── frontend/
│   └── src/
│       ├── app/               # / (storefront) /checkout /gold /pay/[id] /restart-autopay/[id]
│       │                      # /call/[id] (WebRTC phone UI) /dashboard (command center)
│       ├── components/ui/     # menu-item-card, clipped-area-chart, timeline-animation
│       └── lib/               # api client + ws, menu data, utils
├── results/batch_report.json  # committed evidence for the headline numbers
├── .github/workflows/ci.yml   # tests + reproducible batch + frontend type-check
├── render.yaml                # one-click backend deploy; every secret is `sync: false`
├── .gitattributes             # LF in repo, CRLF for .ps1 — clean cross-platform diffs
└── LICENSE                    # MIT
```

## Full-stack setup (optional keys)

Copy `backend/start.example.ps1` → `start.ps1` and fill in what you have. Every key is optional, and the README's claims are all verifiable without any. For live voice: a free Vapi account, a cloudflared quick tunnel (`cloudflared tunnel --url http://localhost:8000`) as `PUBLIC_URL`, and optionally a free Linphone SIP account to make the demo phone actually ring. For real gateway events: Razorpay test-mode keys (no KYC). For the LLM brain: a free Groq key. Frontend env goes in `frontend/.env.local`: `NEXT_PUBLIC_BACKEND_TUNNEL` (tunnel URL, for phone journeys) and `NEXT_PUBLIC_VAPI_PUBLIC_KEY` (Vapi browser key, required for the in-page WebRTC call).

## Deploying it

The backend needs a host with **WebSocket support** (`/ws` streams the audit trail), which rules out serverless-function platforms for it.

**Backend → Render:** New → Blueprint → point at this repo. `render.yaml` declares the build, start command, health check, and every env var as `sync: false`, so each one is prompted for once, stored encrypted, and never committed.

```
start:   uvicorn app.main:app --host 0.0.0.0 --port $PORT
health:  /health
```

**Frontend → Vercel:** Import → Root Directory = `frontend` (Next.js auto-detected). Set these *before* the first build, because `NEXT_PUBLIC_*` values are inlined at build time:

```
NEXT_PUBLIC_BACKEND_TUNNEL=https://<your-service>.onrender.com
NEXT_PUBLIC_VAPI_PUBLIC_KEY=<your Vapi browser key>
```

Then point Vapi's server URL and the Razorpay webhook at the backend's permanent URL. `GET /health` reports database reachability and **which** integrations are configured, never their values. A test enforces that (`tests/test_health.py::test_health_never_leaks_credential_values`).

> On a free tier the backend sleeps after ~15 minutes idle and cold-starts in under a minute; warm it before a demo. SQLite lives on ephemeral disk, so state resets on deploy. That is harmless here, since the headline numbers come from `demo.py`, which builds its own isolated database.

## Honest limitations

- Batch metrics use the deterministic policy table; the LLM routes live traffic only, so **LLM lift over the table is unmeasured** (an A/B batch is the obvious next experiment).
- Recovery success probabilities in the simulator are modeled, not learned from production data; the yield number demonstrates the measurement harness, not a market claim.
- Scheduled retries are recorded intents; a production system needs a real scheduler executing them against stored tokens/mandates.
- Test mode can't exercise live UPI collect or mandate debits; the subscription-save flow simulates the mandate re-authorization.
- Single-merchant, single-process deployment; production needs multi-tenancy, queueing, and idempotent webhook consumption at scale.

## Roadmap to production

Razorpay downtime-webhook-driven bank holds → real retry scheduler with mandate-rule compliance (pre-debit notification windows, RBI caps) → verified WABA + approved templates → learned per-code recovery probabilities from live outcomes → A/B: policy table vs LLM routing on live traffic → promise-to-pay tracking closing the loop.

MIT © 2026 Pari Singhal · built for the Razorpay AI Buildathon (Track 03)
