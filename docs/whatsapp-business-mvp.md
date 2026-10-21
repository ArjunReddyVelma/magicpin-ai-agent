# WhatsApp Business MVP setup

## Scope and safety

The integration accepts **text-only inbound WhatsApp messages**, stores them in the merchant-scoped inbox, generates a suggested reply grounded in that merchant's active context, and sends only after a merchant explicitly selects **Approve & send reply**. Webhook receipt and AI draft generation never send a message automatically. Duplicate Meta message IDs are ignored. Account tokens are encrypted at rest using Fernet and never returned by the API.

## Environment variables

Set these on the backend runtime (never commit real values):

- `WHATSAPP_VERIFY_TOKEN`: a long random value you choose and then enter in Meta webhook configuration.
- `WHATSAPP_APP_SECRET`: the Meta app secret used to verify `X-Hub-Signature-256`.
- `WHATSAPP_ENCRYPTION_KEY`: Fernet key used to encrypt per-merchant access tokens. Generate it with:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `WHATSAPP_GRAPH_API_VERSION`: Graph API version (default `v22.0`).

Keep the encryption key stable; rotating it requires re-encrypting stored tokens before replacing the key. Never paste secrets into GitHub issues, pull-request comments, chat, or source files.

## Configure Meta

1. Create/configure a Meta developer app and add the WhatsApp product.
2. Configure a WhatsApp Business Account and a sender phone number.
3. In the merchant dashboard, open **WhatsApp Inbox** and save the Phone Number ID, optional Business Account ID, and access token. The token is sent only to the authenticated backend and stored encrypted.
4. Deploy the backend to a public HTTPS URL before configuring webhooks. Set callback URL to `https://YOUR_BACKEND_HOST/v1/whatsapp/webhook` and use the exact `WHATSAPP_VERIFY_TOKEN` value as the verification token.
5. Subscribe the Meta app to the `messages` webhook field for the WhatsApp Business Account. Meta will verify the callback with the GET challenge; inbound POST signatures are checked using the app secret.
6. Send a text from a test/approved customer number to the configured WhatsApp number. It should appear in the inbox with an AI draft.
7. Review/edit the draft and press **Approve & send reply**. The backend sends it to the sender ID from that same inbound message and records the provider message ID and send status.

## API endpoints

- `GET /v1/whatsapp/account`: current merchant's connection status; never returns token.
- `PUT /v1/whatsapp/account`: save/update current merchant's WhatsApp account (authenticated + CSRF).
- `GET /v1/whatsapp/messages`: current merchant's inbox only.
- `POST /v1/whatsapp/messages/{message_id}/send`: explicit human-approved send (authenticated + CSRF).
- `GET /v1/whatsapp/webhook`: Meta webhook challenge.
- `POST /v1/whatsapp/webhook`: signature-verified Meta events.

## MVP limitations

Text messages only; media/voice, templates/campaigns, automated sends, and delivery-status reconciliation are not included. Meta credentials and public HTTPS webhook setup are required before a real end-to-end test. Do not deploy until tests and code review pass.
