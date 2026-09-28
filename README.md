# Offline order-support chatbot reference

An original public reference using only synthetic fixtures. This is not client
work, a client delivery, or a production-ready bot. It demonstrates how a support
conversation can answer repetitive order-status and return-eligibility questions
while keeping account authorization outside model decisions.

## Run

Python 3.11 or newer; standard library only. No install, account, credentials,
environment configuration, or network access is required. From this directory:

```sh
python3 -m chatbot demo
python3 -m unittest discover -v
```

Both the demo and tests block socket connection attempts. The demo output is
compared byte-for-byte with `tests/golden_transcript.txt` by the test suite.
`.env.example` is a names-only inventory for possible future adapters; it is
not a configuration file to source. Nothing loads environment variables.

## Example

```text
You: status
Bot: Which order? Use an ID like ORD-101.
You: ORD-101
Bot: ORD-101: delivered.
You: Can I return it?
Bot: ORD-101: eligible for a return in this fixture.
```

Try the scripted demo for reset, order-first clarification, and denied access.
Supported mock vocabulary includes `status`, `where`, `return`, and order IDs
such as `ORD-101`. `cancel`, `/cancel`, `reset`, and `/reset` clear context.
Multiple distinct order IDs prompt clarification. Unrecognized text prompts help
without reading a remembered order. This is deterministic keyword matching:
MockProvider does not reason or understand arbitrary natural language.

## Architecture and boundaries

1. A Telegram-shaped dictionary enters `Bot.handle` alongside an independently
   supplied trusted fixture transport handle.
2. The fixed handle registry maps to a principal and private chat. Unknown
   handles, mismatched chats, malformed IDs, empty text, and text over 1000
   Unicode characters are rejected. Envelope `from.id` is never authentication.
3. An immutable conversation snapshot supplies remembered intent/order; idle
   context expires after 300 monotonic seconds. Reset and expiry do not clear
   message-order protections.
4. `LLMProvider` returns a strict decision with only `intent` and `order_id`.
   MockProvider validates its output, and the orchestrator validates every
   provider output again. There is no provider-controlled principal or reply.
5. The authorized order fixture checks ownership before fetching data, on every
   attempt. Alice has ORD-101/102; Bob has ORD-201. Missing and foreign orders
   receive the same response. Eligibility is a synthetic boolean, not a policy
   calculation, refund action, or promise about an actual purchase.
6. API data is validated and rendered through fixed templates; replies are at
   most 240 characters. Logs contain only fixed JSON event labels, without
   identities, message text, order IDs, secrets, or exception details.

Reads retry only `TransientAPIError`, with two total attempts and one injected
0.1-second backoff (default `time.sleep`). All other failures are terminal for
that update. An injected monotonic clock enforces a cooperative five-second
budget, checked before/after provider work and API attempts and after backoff.
It includes lock wait, but cannot interrupt a blocked lock, provider, read, or
sleep. A future adapter must implement its own bounded I/O timeouts; this is
not a hard wall-clock guarantee.

## Delivery and state limits

A process-local lock serializes state transitions and reads, including concurrent
duplicate deliveries. The default dedup cache retains at most 128 update keys.
Per-principal update/message high-water marks reject stale or out-of-order IDs
even after cache eviction or conversation expiry. Session and watermark storage
are bounded by the two fixed fixture principals. Out-of-order messages are
discarded, not reordered. Duplicates return an ignored acknowledgement, not a
cached answer. Accepted IDs are consumed even if processing fails: retry with a
new message ID and update ID.

Everything is in memory. Restart loses sessions, deduplication, and watermarks;
multiple processes do not coordinate. There is no durable delivery, exactly-once
claim, Telegram send/reply API, webhook, polling, live order API, or live LLM.
This sequential design prioritizes inspectability over throughput.

OpenAI and Telegram adapters are explicitly deferred and unsupported. A future
LLM adapter would implement `LLMProvider` and still pass the same validator.
A future Telegram adapter must authenticate transport ingress, establish a
verified account binding outside message/model data, and supply trusted context;
the public fixture handle strings are test inputs, not credentials. Live work
also needs durable replay protection, rate limits, operational monitoring,
privacy controls, and independent security review. No live behavior was tested.

Tests cover conversations, isolation and forgery attempts, invalid decisions and
API data, size limits, retry/deadline behavior, concurrent duplicates, stale
messages, log sanitation, and the golden transcript. See `SECURITY.md` for the
threat boundary. All source and data were created for this reference; no private
code, business records, infrastructure topology, or production URLs are included.
