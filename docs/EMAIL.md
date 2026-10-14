# Sending email

V-Base can hand a message to a transactional email provider so a follow-up goes
out from the contact record instead of from a separate mail client. Sending is
**optional**: with no provider configured the CRM works exactly as before and
the compose dialog explains what is missing.

---

## 1. How it works

| Piece | Where |
|---|---|
| Provider dispatch | `backend/src/nexus/core/email.py` |
| Gmail API client | `backend/src/nexus/core/gmail.py` |
| Delivery webhooks | `backend/src/nexus/core/email_webhooks.py` |
| Sequences | `backend/src/nexus/core/sequences.py` |
| Endpoints | `backend/src/nexus/api/v1/email.py` |
| Compose dialog | `apps/web/src/components/crm/email-composer.tsx` |
| Default provider | [Resend](https://resend.com) |
| Alternative provider | Gmail API (send-only OAuth scope) |

A send is a normal request/response — the provider is called while the user
waits, so a rejected domain or an invalid recipient surfaces immediately as a
toast rather than disappearing into a queue. There is no background worker and
no retry loop.

Every accepted message is appended to the activity trail
(`action="email_sent"`) and therefore appears:

* on the contact's **Emails** card,
* in the global **Activity** feed,
* in `GET /api/v1/email/messages`.

---

## 2. Configuration

Create a provider account, verify the sending domain, then set:

| Variable | Required | Notes |
|---|---|---|
| `EMAIL_API_KEY` | yes | Provider secret. Never returned by the API. |
| `EMAIL_FROM` | yes | Must be a verified sender or domain, e.g. `V-Base <crm@example.com>`. |
| `EMAIL_PROVIDER` | no | Defaults to `resend`. |
| `EMAIL_FROM_NAME` | no | Display name; defaults to `APP_NAME`. |
| `EMAIL_REPLY_TO` | no | Defaults to nothing. |
| `EMAIL_TIMEOUT_SECONDS` | no | Provider HTTP timeout, default `15`. |

Environment values win; a value stored in the settings table fills the gap. That
ordering means a deployment can inject the secret while an administrator supplies
`email_from` from **Settings → General** without a restart.

> The API key is write-only. `GET /api/v1/email/status` reports whether a key was
> found and whether it came from the environment or the settings table — never
> the key itself.

---

## 3. Gmail instead of Resend

Set `EMAIL_PROVIDER=gmail` (or pick it in **Settings → General**) to send from
your own mailbox through the Gmail API. This is a real OAuth flow, not an app
password:

1. In Google Cloud, create an OAuth client of type **Web application** and
   enable the **Gmail API**.
2. Add an authorised redirect URI of `<your API origin>/api/v1/email/gmail/callback`.
3. Set `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` (environment or settings keys).
4. In **Settings → General**, press **Connect Gmail**. The consent screen is
   scoped to `gmail.send` — V-Base can send, and cannot read, delete or change
   anything else in the mailbox.
5. The returned **refresh token** is stored in the settings table. Access tokens
   are cached in-process and refreshed on demand, so a batch of sends performs
   one token exchange.

The callback returns the administrator to the origin that started the flow when
that origin is already in `ALLOWED_ORIGINS` (signed into the `state` parameter,
so it cannot be redirected elsewhere). Otherwise it falls back to `FRONTEND_URL`.

## 4. Delivery tracking

Sending only proves the provider *accepted* the message. To learn what happened
next, set `EMAIL_WEBHOOK_SECRET` to the signing secret (`whsec_...`) from your
provider's webhook settings and point the webhook at:

```
<your API origin>/api/v1/email/webhook/resend
```

* Resend signs with **Svix**: HMAC-SHA256 over `<id>.<timestamp>.<body>`, with a
  five-minute timestamp tolerance so a captured request stops being replayable.
* An unsigned or tampered event is refused (`401`). With no secret configured the
  endpoint answers `503` rather than accepting unverified events.
* Recognised events (`delivered`, `opened`, `clicked`, `bounced`, `complained`,
  `delivery_delayed`, `failed`) update the message's status; a bounce always wins
  over a later open. Unrecognised event types are recorded but leave the status
  alone, so a new provider event cannot blank out a known outcome.
* Every event is appended to the message's `events` list, giving an audit trail
  per send.

Because the provider posts server-to-server, this path is exempt from the
CSRF/origin middleware (`_SIGNATURE_VERIFIED_PREFIXES` in `core/middleware.py`).
That exemption is scoped to the webhook prefix only, and is safe only because the
handler verifies the signature before acting on anything.

## 5. Email sequences

A sequence is a short series of follow-ups — write them once, enroll a contact,
and the second and third touch go out on their own. **Sequences are the one part
of this module that acts without being asked**: the app runs a poll loop
(`nexus/core/sequences.py`) that sends whatever has come due.

| Piece | Where |
|---|---|
| Rendering and dispatch | `backend/src/nexus/core/sequences.py` |
| Tables | `email_sequences`, `email_sequence_steps`, `email_sequence_enrollments` |
| Endpoints | `backend/src/nexus/api/v1/sequences.py` |
| Page | `apps/web/src/pages/sequences.tsx` |
| Contact card | `apps/web/src/components/crm/contact-sequences.tsx` |

**Steps and delays.** Step 0's `delay_days` is the wait *before* it, so a delay
of 0 sends as soon as the contact is enrolled; each later step waits its own
`delay_days` from the moment the previous one went out. Editing a sequence
changes what the remaining steps of live enrollments will send — steps already
sent are not recalled.

**Merge fields.** `{{first_name}}`, `{{last_name}}`, `{{full_name}}`,
`{{email}}`, `{{job_title}}`, `{{company}}`, `{{city}}`, `{{country}}`. Missing
fields render empty; an unknown token is left exactly as written, so a typo is
obvious in the preview instead of silently blanked. `first_name`/`last_name`
fall back to splitting `full_name`, because most CRM records carry only a full
name.

**Enrollment lifecycle.** `active` → `paused` → `active`, or `cancelled` (final).
A contact may hold one *live* enrollment per sequence; after a sequence completes
or is cancelled they can be enrolled again. Pausing a sequence parks everyone in
it without editing each enrollment. Resuming re-anchors the cadence to the moment
of resuming, so a week on pause does not fire every remaining step at once.

**When a send fails** the enrollment is marked `failed` with the reason in
`last_error` rather than retried: the realistic refusals (unverified domain,
invalid recipient) do not fix themselves, and retrying with no backoff would
hammer the provider. A contact whose email was removed after enrolling fails the
same way.

**Two honest caveats**, both bounded:

* A crash between the provider accepting a message and the enrollment being
  advanced re-sends that step. At-least-once is the right trade for a follow-up
  email — a duplicate is visible, a silently dropped step is not. `FOR UPDATE
  SKIP LOCKED` stops two replicas claiming the same enrollment at once.
* The loop is single-process and in-memory. A deployment that would rather drive
  sends from cron sets `SEQUENCES_POLL_ENABLED=false` and calls
  `POST /api/v1/sequences/dispatch` itself.

| Variable | Default | Notes |
|---|---|---|
| `SEQUENCE_POLL_SECONDS` | `60` | How often the dispatcher looks for due steps. |
| `SEQUENCE_BATCH_SIZE` | `25` | Steps sent per poll. |
| `SEQUENCES_POLL_ENABLED` | `true` | `false` disables the in-process loop. |

---

## 6. Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/email/status` | Whether sending is possible, and what is missing |
| `POST` | `/api/v1/email/send` | Send one message (`to`, `subject`, `text`, optional `html`, `reply_to`, `contact_id`) |
| `GET` | `/api/v1/email/messages` | Recent sends with delivery status, optionally filtered by `contact_id` |
| `GET` | `/api/v1/email/gmail/authorize` | Start the Gmail consent flow (superuser) |
| `GET` | `/api/v1/email/gmail/callback` | OAuth callback; stores the refresh token (superuser) |
| `POST` | `/api/v1/email/gmail/disconnect` | Forget the stored refresh token (superuser) |
| `POST` | `/api/v1/email/webhook/{provider}` | Delivery events (signature required, no session) |
| `GET` | `/api/v1/sequences` | Sequences with their steps and enrollment counts |
| `POST` | `/api/v1/sequences` | Create a sequence (`name`, `description`, `steps`) |
| `GET` | `/api/v1/sequences/{id}` | One sequence |
| `PATCH` | `/api/v1/sequences/{id}` | Rename, pause, or replace the step list |
| `DELETE` | `/api/v1/sequences/{id}` | Delete a sequence, its steps and its enrollments |
| `GET` | `/api/v1/sequences/enrollments` | Enrollments, filterable by `contact_id` / `sequence_id` / `status` |
| `PATCH` | `/api/v1/sequences/enrollments/{id}` | Pause, resume or cancel one enrollment |
| `POST` | `/api/v1/sequences/{id}/enroll` | Enroll a contact (`contact_id`) |
| `POST` | `/api/v1/sequences/{id}/preview` | Render the steps against a contact, without sending |
| `POST` | `/api/v1/sequences/dispatch` | Send everything that is due right now |

`POST /email/send` answers with:

* **201** — accepted by the provider, with its message id;
* **400** — not configured, or an unknown `contact_id`;
* **422** — the payload failed validation (bad address, empty subject);
* **502** — the provider refused; `detail` carries the provider's own message.

---

## 7. Adding another provider

`_JSON_PROVIDERS` in `nexus/core/email.py` maps a provider name to its send URL.
The request shape used there — a JSON body with `from`, `to`, `subject`, `text`
— is the same for the mainstream transactional APIs, so adding one is an entry in
that mapping. A provider with a different shape (like Gmail) gets a small branch
in `send_message` plus its own module. If it signs webhooks differently, add a
verifier in `nexus/core/email_webhooks.py` and list it in
`SUPPORTED_WEBHOOK_PROVIDERS`.
