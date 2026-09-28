# Security scope

This is a synthetic offline reference, not a deployed service or client system.
Do not use real tokens, personal information, or real order data with the demo.
`.env` and `.env.*` are ignored except the names-only `.env.example` inventory.

Untrusted inputs include the entire Telegram-shaped update, text, provider
decisions, and order response data. Only the separately supplied transport handle
selects one of two fixed synthetic principals. A caller able to choose that
trusted argument can impersonate a fixture user: it is deliberately not a live
authentication mechanism. Message `from.id`, extra principal/owner fields, and
model text cannot override the binding. Private-chat matching is an additional
check, not proof of sender identity.

The fixture API authorizes before fetching. Provider output cannot invoke
arbitrary tools, execute code, change ownership, or supply user-facing text.
Only allowlisted decision fields and validated response templates are accepted.
Replies and input are bounded by character count; a future HTTP transport must
also bound request bytes and parsing resources before constructing dictionaries.

Logging is opt-in via Python logging configuration and emits fixed event JSON.
No payload, identity, order identifier, exception message, or traceback is logged
by this application. Future adapters must preserve these restrictions.

Cooperative deadlines cannot terminate blocked I/O. Process-local locking and
bounded deduplication provide no restart or multi-process guarantees. Neither
the demo nor tests prove production authentication, delivery, isolation against
malicious in-process Python code, availability, or live provider safety. Socket
blocking verifies the exercised paths avoid outbound connections; it is not an
OS sandbox. A live adapter and independent review are required before any live
use, with durable replay controls and actual transport authentication.

For a suspected vulnerability, contact the repository maintainer privately
through the hosting platform when available. Do not include credentials or
personal information in public issues. No dedicated security mailbox or response
SLA is claimed for this reference.
