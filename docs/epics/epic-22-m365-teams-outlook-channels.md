# Epic 22: MS Teams + Outlook als Communication-Gateway-Channels (analog Telegram)

## Context

Der Agent soll genauso über **Microsoft Teams** und **Outlook (E-Mail)**
kommunizieren wie heute über Telegram: bi-direktional, mit eigener
M365-Identität (z. B. `agent@firma.de`), über `/link <code>` an einen User
gebunden, integriert in den **Communication Gateway**.

Heute existiert für Teams nur ein Stub, für Outlook gar nichts:

- `TeamsOutboundSender.send()` (`src/taskforce/infrastructure/communication/outbound_senders.py:468-523`) — loggt nur `"not implemented"`.
- `TeamsInboundAdapter.verify_signature()` (`src/taskforce/infrastructure/communication/inbound_adapters.py:133-195`) — gibt immer `True` zurück (keine JWT-Validierung).
- `gateway_registry.py:74-82` — Teams-Sender-Builder gibt `None` zurück (Multi-Bot-Teams "follow-up").
- Outlook: **kein** Inbound-Adapter, **kein** Outbound-Sender, **kein** Channel-Eintrag.

Beide Channels sollen **delegated** (Signed-in Bot, OAuth Device/Auth-Code) und
**application** (Client-Credentials) als Auth-Modus unterstützen. Bestehende
Microsoft-OAuth-Endpoints (`oauth2_device_flow.py:34-46`) werden wiederverwendet.

Die Telegram-Integration (`TelegramInboundAdapter`, `TelegramOutboundSender`,
`BotConfig(channel_type="telegram")`, Webhook-Route, `/link`-Flow) ist das
**Referenz-Muster** — jeder neue Channel folgt identisch dem gleichen Schema.

---

## Phase 1 — Microsoft Teams Channel

### 1.1 Auth-Bridge (Bot-Framework-Token)

Bot Framework verwendet **eigenen** OAuth (`https://login.botframework.com`) für
Service-to-Service-Calls — **nicht** identisch mit Graph-OAuth.

Files:
- `src/taskforce/infrastructure/auth/bot_framework_token_provider.py` — **neu**.
  Hält App-ID + App-Password, ruft `POST https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token` (grant_type=client_credentials, scope=`https://api.botframework.com/.default`), cached Token bis kurz vor Expiry. Async, thread-safe.
- Wird **innerhalb des `TeamsOutboundSender`** instanziiert (per Bot), nicht über den globalen AuthManager — semantisch eigener Auth-Kanal.

### 1.2 TeamsOutboundSender real implementieren

Datei: `src/taskforce/infrastructure/communication/outbound_senders.py:468-523`

- Konstruktor zusätzlich: `conversation_reference_store: TeamsConversationReferenceStore`.
- `send(recipient_id, content, conversation_id, …)`:
  1. ConversationReference für `conversation_id` aus dem Store laden (enthält `service_url`, `bot.id`, `conversation.tenant_id`).
  2. Bot-Framework-Bearer-Token holen (Schritt 1.1).
  3. `POST {service_url}/v3/conversations/{conversation_id}/activities` mit `Activity{type:"message", text:content, from, recipient, conversation}`.
  4. Activity-ID + Timestamp zurückgeben.
- `send_file(...)`: Activity mit `attachments=[{contentUrl, contentType, name}]` oder als Teams-Adaptive-Card (Phase 1.b — initial nur Text).
- Fehlermodi: 401 → Token-Cache invalidieren + 1 Retry; 429 → Retry-After respektieren.

### 1.3 ConversationReferenceStore

**Warum:** Für proaktive Nachrichten (`send_notification`-Tool / Gateway-Broadcast) braucht Teams die Conversation-Reference aus einer **vorherigen** Nachricht — anders als Telegram, wo `chat_id` reicht.

Files:
- `src/taskforce/core/interfaces/teams_conversation_reference.py` — **neu**. Protocol:
  ```python
  class TeamsConversationReferenceProtocol(Protocol):
      async def save(self, channel_id: str, ref: dict) -> None: ...
      async def load(self, channel_id: str) -> dict | None: ...
      async def list_for_user(self, channel_id: str) -> list[dict]: ...
  ```
- `src/taskforce/infrastructure/communication/teams_conversation_reference_store.py` — **neu**. File-basiert unter `<work_dir>/teams_conversations/{bot_id}/{conversation_id}.json`. Atomic writes, asyncio.Lock. Enterprise-Plugin kann via `infrastructure_overrides.set_teams_conversation_reference_store_override` ersetzen (Pattern aus `application/infrastructure_overrides.py`).
- Capture-Punkt: `TeamsInboundAdapter.normalize()` schreibt die Reference (`metadata.conversation_reference`) → `CommunicationGateway` ruft `store.save()` vor Agent-Aufruf.

### 1.4 TeamsInboundAdapter: echte JWT-Validierung

Datei: `src/taskforce/infrastructure/communication/inbound_adapters.py:133-195`

- `verify_signature(payload, headers)`:
  1. `Authorization: Bearer <jwt>` extrahieren.
  2. OpenID-Config + JWKS von `https://login.botframework.com/v1/.well-known/openidconfiguration` laden (mit 24h-Cache).
  3. JWT verifizieren: Issuer = `https://api.botframework.com`, Audience = eigene App-ID, Signatur via `cryptography`/`PyJWT`.
  4. Bei Fail: `False` zurückgeben → Route antwortet 401.
- Neue Dependency: `PyJWT[crypto]` in `pyproject.toml` (vermutlich bereits über `cryptography` extra dabei — verifizieren).

### 1.5 Gateway-Wiring

Datei: `src/taskforce/infrastructure/communication/gateway_registry.py:74-82`

- `_build_sender_for_bot()`: Teams-Zweig nicht mehr `return None`, sondern:
  ```python
  if bot.channel_type == "teams" and bot.bot_token and bot.app_id:
      return TeamsOutboundSender(
          app_id=bot.app_id,
          app_password=bot.bot_token,
          conversation_reference_store=teams_ref_store,
      )
  ```
- `BotConfig` (`core/domain/settings.py`) braucht ein zusätzliches Feld `app_id: str | None` für Teams (Telegram hat nur `bot_token`).
- Legacy-Env-Fallback (`gateway_registry.py:227-242`) bleibt unverändert.
- Webhook-Route `POST /api/v1/gateway/teams/webhook` (`api/routes/gateway.py:271-358`) ist bereits generisch — funktioniert automatisch.

### 1.6 Tests

- `tests/unit/taskforce_extensions/infrastructure/test_outbound_senders.py` — Teams-Send mit Mock-`httpx`-Client + Mock-Token-Provider.
- `tests/unit/taskforce_extensions/infrastructure/test_inbound_adapters.py:54-90` erweitern — echte JWT mit Test-JWKS, Negative-Tests (falscher Issuer, abgelaufen, falsche Audience).
- `tests/unit/infrastructure/communication/test_teams_conversation_reference_store.py` — neu.

---

## Phase 2 — Outlook Channel

### 2.1 Channel-Typ + BotConfig-Erweiterung

Datei: `src/taskforce/core/domain/settings.py`

- `BotConfig` zusätzliche Felder (optional, Outlook-spezifisch):
  - `tenant_id: str | None` — Microsoft Tenant.
  - `mailbox: str | None` — z. B. `agent@firma.de`.
  - `auth_mode: Literal["delegated", "client_credentials"] | None` — wählt Token-Quelle.
  - `inbound_mode: Literal["webhook", "polling"] = "polling"` — Polling für lokale Entwicklung Default, Webhook für Prod.
- `parse_channels_section()` (`infrastructure/communication/gateway_registry.py`) entsprechend erweitern; Tests in `tests/unit/core/domain/test_settings_bot_config.py` ergänzen.

### 2.2 OutlookOutboundSender (Microsoft Graph)

Files:
- `src/taskforce/infrastructure/communication/outbound_senders.py` — neue Klasse `OutlookOutboundSender(OutboundSenderProtocol)`:
  - Konstruktor: `mailbox`, `auth_mode`, `tenant_id`, Referenz auf `AuthManager` (für Token-Refresh).
  - `send(recipient_id, content, conversation_id, …)`:
    1. Token holen: `auth_manager.get_token("microsoft", scope_preset=...)` (delegated) oder Client-Credentials-Flow (Schritt 3.1).
    2. **Neue Threads:** `POST https://graph.microsoft.com/v1.0/me/sendMail` (delegated) bzw. `/users/{mailbox}/sendMail` (app) mit Body `{message:{subject, body:{contentType:"Text", content}, toRecipients:[{emailAddress:{address: recipient_id}}]}, saveToSentItems:true}`. `conversationId` ist in Graph read-only und wird **nicht** im Payload gesetzt — Microsoft leitet ihn server-seitig aus den `internetMessageHeaders` ab.
    3. **Replies in bestehende Threads** (wenn `conversation_id` bekannt): bevorzugt `POST /me/messages/{originalMessageId}/reply` (oder `/replyAll`) — Microsoft Graph setzt `In-Reply-To`/`References` und den `conversationId` automatisch. Fallback bei reinem Mail-Thread ohne bekannte Source-Message-ID: `sendMail` mit manuell gesetzten `internetMessageHeaders` (`In-Reply-To` + `References`) im `message`-Objekt.
  - `send_file(...)`: `attachments` Array.

> **Designentscheidung:** Mail-Transport läuft über Microsoft Graph, nicht über
> den Azure-Bot-„Email"-Channel. Graph gibt volle Kontrolle über Threading,
> HTML, Attachments und braucht keine zusätzliche Azure-Bot-Channel-Aktivierung.

### 2.3 OutlookInboundAdapter

Datei: `src/taskforce/infrastructure/communication/inbound_adapters.py`

- Neue Klasse `OutlookInboundAdapter(InboundAdapterProtocol)`. Normalisiert zwei Eingabe-Shapes:
  - **Webhook (Graph Change Notification)**: `{value: [{subscriptionId, clientState, resource, resourceData:{id}, changeType}]}` → Resource per Graph nachladen (`GET /me/messages/{id}`).
  - **Polling**: direkt Graph-Message-Objekt.
- Normalisiert auf `InboundMessage(conversation_id=conversationId, message=body.content, sender_id=from.emailAddress.address, metadata={subject, message_id, internet_message_id, references})`.
- `verify_signature()`: vergleicht `clientState` aus Notification mit dem beim Subscription-Setup gespeicherten HMAC.

### 2.4 Inbound-Modi

Datei: `src/taskforce/infrastructure/communication/outlook_inbound.py` — **neu**, zwei Komponenten:

**(a) Polling (Default für lokal):**
- Klasse `OutlookPoller` — Background-asyncio-Task im FastAPI-Lifespan (`api/server.py`).
- Pollt `GET /me/messages?$filter=isRead eq false&$top=25` alle N Sek.
- Pro Message: `gateway.handle_inbound(channel="outlook", payload=msg, ...)` aufrufen (gleicher Codepfad wie Webhook).
- Markiert verarbeitete Mails als `isRead=true`.
- Pro Bot eine Instanz; Lifecycle an Bot-Enabled-Status gekoppelt.

**(b) Webhook (für Prod / Public HTTPS):**
- Klasse `OutlookSubscriptionManager`:
  - Erstellt Graph Subscription: `POST /subscriptions {changeType:"created", notificationUrl:"<public>/api/v1/gateway/outlook/webhook", resource:"/me/mailFolders('Inbox')/messages", expirationDateTime:+2.5d, clientState:<hmac>}`.
  - Renewal-Loop alle 2 Tage (Subscription läuft nach max. 3 Tagen ab).
  - Subscription-State persistent unter `<work_dir>/outlook_subscriptions/{bot_id}.json`.
- Existierende generische Route `POST /api/v1/gateway/outlook/webhook` (`api/routes/gateway.py:271-358`) funktioniert ohne Änderung — Microsoft sendet allerdings auch einen **Validation-Request** (`?validationToken=...`), der wörtlich zurückgegeben werden muss. Route generisch erweitern: vor `adapter.normalize()` `request.query_params.get("validationToken")` prüfen und ggf. als `text/plain` zurückgeben.

### 2.5 Gateway-Wiring

Datei: `src/taskforce/infrastructure/communication/gateway_registry.py`

- `_build_sender_for_bot()` neuer Zweig:
  ```python
  if bot.channel_type == "outlook" and bot.mailbox:
      return OutlookOutboundSender(
          mailbox=bot.mailbox,
          auth_mode=bot.auth_mode or "delegated",
          tenant_id=bot.tenant_id,
          auth_manager=auth_manager,
      )
  ```
- `_build_inbound_adapter_for_bot()`: `OutlookInboundAdapter` registrieren.
- Beim Build: für jeden Outlook-Bot mit `inbound_mode="polling"` einen `OutlookPoller` starten (Hook in `build_gateway_components()` Rückgabewert ergänzen, in `api/server.py` Lifespan starten/stoppen).
- Für `inbound_mode="webhook"`: beim ersten Start `OutlookSubscriptionManager.ensure_subscription()` aufrufen.

### 2.6 Tests

- `tests/unit/taskforce_extensions/infrastructure/test_outlook_outbound_sender.py` — Mock-Graph, beide Auth-Modi, Reply-Thread.
- `tests/unit/taskforce_extensions/infrastructure/test_outlook_inbound_adapter.py` — Polling-Shape, Webhook-Shape, Validation-Token, falscher clientState.
- `tests/unit/infrastructure/communication/test_outlook_subscription_manager.py` — Create + Renew.
- `tests/unit/infrastructure/communication/test_outlook_poller.py` — Mark-as-read, since_last_check, gateway.handle_inbound aufgerufen.

---

## Phase 3 — Auth-Erweiterung (gemeinsam für Teams + Outlook)

### 3.1 Client-Credentials-Flow

Files:
- `src/taskforce/infrastructure/auth/oauth2_client_credentials_flow.py` — **neu**, implementiert `AuthFlowProtocol` mit `flow_type = "oauth2_client_credentials"`. POSTet an `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token` mit `grant_type=client_credentials, scope=https://graph.microsoft.com/.default`. Keine Refresh-Tokens — Manager re-runs den Flow bei Expiry.
- `src/taskforce/application/auth_manager.py` — Flow registrieren, Refresh-Logik: bei abgelaufenem Token ohne refresh_token → falls `flow_type == client_credentials`, Flow erneut ausführen.

### 3.2 Scope-Presets

Files:
- `src/taskforce/infrastructure/auth/microsoft_scopes.py` — **neu**:
  - `TEAMS_DELEGATED = ["ChatMessage.Send", "Chat.ReadWrite", "User.Read", "offline_access"]`
  - `OUTLOOK_DELEGATED = ["Mail.Send", "Mail.ReadWrite", "User.Read", "offline_access"]`
  - `GRAPH_APP = ["https://graph.microsoft.com/.default"]` (Application-Permissions per Admin-Consent: `Mail.Send`, `Mail.ReadWrite`).
- `agents/butler/src/taskforce_butler/infrastructure/tools/auth_tool.py:40-81` — Tool-Schema erweitern: `flow_type` Enum um `"oauth2_client_credentials"`, optionale Felder `tenant_id`, `scopes_preset`.

### 3.3 Settings-Hydration

Datei: `src/taskforce/application/settings_hydrator.py:96-99`

- Mapping um Outlook erweitern:
  ```python
  "outlook": {
      "mailbox": "OUTLOOK_MAILBOX",
      "tenant_id": "OUTLOOK_TENANT_ID",
      "client_id": "OUTLOOK_CLIENT_ID",
      "client_secret": "OUTLOOK_CLIENT_SECRET",
  }
  ```
- Teams-Mapping bleibt unverändert (`TEAMS_APP_ID`, `TEAMS_APP_PASSWORD`), Tenant aus Bot-Config.

---

## Phase 4 — Profile, Docs, Manifest

### 4.1 Settings-UI

Datei: `ui/src/features/settings/ChannelsTab.tsx` (oder analog)

- Bestehender Tab "Channels" um Teams- und Outlook-Sektionen erweitern (Telegram-Block als Vorlage).
- Felder Teams: App-ID, App-Password, Tenant-ID, "Test Send"-Button (POST `/api/v1/settings/channels/teams/test`).
- Felder Outlook: Mailbox, Tenant-ID, Auth-Modus, Inbound-Modus, Client-ID/Secret (nur bei client_credentials), "Authenticate"-Button (löst OAuth-Device-Flow aus, zeigt URL+Code an), "Test Send".

### 4.2 Profil-Beispiel

Datei: `agents/butler/configs/butler.agent.md` — Doku-Snippet für `channels:`-Block ergänzen (Beispiel Teams + Outlook).

### 4.3 Docs + ADR

Files:
- `docs/integrations.md` — neue Sektionen **"Microsoft Teams Channel"** und **"Outlook Channel"** mit:
  - M365-Service-Account anlegen + Lizenz (Business Basic).
  - Azure-Bot-Ressource (für Teams) — App-Registrierung, Channel "Microsoft Teams" aktivieren.
  - Entra-ID-App (für Outlook) — Permissions Mail.Send/Mail.ReadWrite (delegated und/oder app), Admin-Consent.
  - Tunneling für lokale Entwicklung (ngrok / Dev Tunnels) — nur für Teams + Outlook-Webhook-Modus.
  - Outlook-Polling-Modus (kein Tunnel nötig) als Default für lokale Entwicklung.
- `docs/integrations/teams_app_manifest.json` — **neu**, Template für Teams-App-Manifest (Name, Icon, Bot-ID).
- `docs/adr/adr-026-m365-channels.md` — **neu**, ADR mit Entscheidungen: Polling-Default lokal, Graph-Subscriptions für Prod, Bot-Framework-Token separat vom Graph-Token, delegated+app dual-mode, Graph statt Azure-Bot-Email-Channel.

---

## Critical Files

### Neu
- `src/taskforce/infrastructure/auth/oauth2_client_credentials_flow.py`
- `src/taskforce/infrastructure/auth/bot_framework_token_provider.py`
- `src/taskforce/infrastructure/auth/microsoft_scopes.py`
- `src/taskforce/core/interfaces/teams_conversation_reference.py`
- `src/taskforce/infrastructure/communication/teams_conversation_reference_store.py`
- `src/taskforce/infrastructure/communication/outlook_inbound.py` (Poller + SubscriptionManager)
- `docs/integrations/teams_app_manifest.json`
- `docs/adr/adr-026-m365-channels.md`

### Erweitern
- `src/taskforce/infrastructure/communication/outbound_senders.py` (TeamsOutboundSender real, OutlookOutboundSender neu)
- `src/taskforce/infrastructure/communication/inbound_adapters.py` (TeamsInboundAdapter JWT, OutlookInboundAdapter neu)
- `src/taskforce/infrastructure/communication/gateway_registry.py` (Teams-Sender freischalten, Outlook-Wiring, Poller-Lifecycle)
- `src/taskforce/core/domain/settings.py` (BotConfig: `app_id`, `tenant_id`, `mailbox`, `auth_mode`, `inbound_mode`)
- `src/taskforce/application/auth_manager.py` (Client-Credentials-Flow registrieren)
- `src/taskforce/application/settings_hydrator.py` (Outlook-Mapping)
- `src/taskforce/api/routes/gateway.py` (Validation-Token-Handling im Webhook)
- `src/taskforce/api/server.py` (Lifespan startet/stoppt OutlookPoller)
- `agents/butler/src/taskforce_butler/infrastructure/tools/auth_tool.py` (flow_type, scopes_preset)
- `docs/integrations.md`
- `agents/butler/configs/butler.agent.md`

## Wiederverwendung

- `TelegramInboundAdapter` + `TelegramOutboundSender` als **strukturelles Vorbild** (gleiche Protocols, gleicher Lifecycle, gleiche Tests).
- `/link <code>` Flow (`application/gateway.py:416-421`) funktioniert für jeden neuen Channel **out of the box** — ein User bindet `(channel, sender_id)` → `(tenant, user)`.
- `CommunicationGateway`, `RecipientResolver`, `ConversationStore`, `ChannelLinkRegistry` bleiben unverändert.
- `OAuth2DeviceFlow` + `OAuth2AuthCodeFlow` (Microsoft-Endpoints bereits konfiguriert).
- `EncryptedTokenStore` (`infrastructure/auth/encrypted_token_store.py`) für alle drei Token-Typen (Graph delegated, Graph app, Bot Framework).
- Generische Webhook-Route `POST /api/v1/gateway/{channel}/webhook` deckt Teams und Outlook ab.
- `send_notification`-Tool funktioniert automatisch, sobald die Sender real sind.

## Verification

1. **Unit-Tests grün:** `uv run pytest tests/unit/taskforce_extensions/infrastructure/test_outbound_senders.py tests/unit/taskforce_extensions/infrastructure/test_inbound_adapters.py tests/unit/infrastructure/communication/`
2. **Lint/Type:** `uv run black src tests`, `uv run ruff check`, `uv run mypy src/taskforce`.
3. **Teams End-to-End (manuell):**
   - M365-Account `agent@firma.de` + Azure Bot + App-Registrierung (per Runbook).
   - Tunnel via Dev Tunnel / ngrok, Messaging-Endpoint in Azure Bot eintragen.
   - Teams-App-Manifest sideloaden, Agent in Chat hinzufügen.
   - Nachricht senden → Agent antwortet im selben Chat.
   - `/link <code>` → Sender wird an Test-User gebunden.
4. **Outlook Polling End-to-End (lokal, ohne Tunnel):**
   - Entra-App + delegated Auth via `/authenticate microsoft --flow oauth2_device --scopes-preset outlook_delegated`.
   - `taskforce` Server starten, Outlook-Channel in Settings aktivieren (Inbound-Modus = polling).
   - Mail an `agent@firma.de` schicken → Agent antwortet als Reply mit korrektem `In-Reply-To`-Header.
5. **Outlook Webhook End-to-End:** Tunnel hochziehen, Inbound-Modus auf `webhook` stellen → Subscription wird erstellt, Microsoft sendet `validationToken` (Server antwortet 200 text/plain) → Mail-Notification triggert Agent-Antwort. Renewal-Loop verlängert Subscription nach 2 Tagen.
6. **Send_notification proaktiv:** `taskforce run mission "Schicke eine Test-Push an mich" --profile butler` → Push wahlweise über Telegram, Teams oder Outlook (je nach `channels:`-Konfiguration des Recipients).
