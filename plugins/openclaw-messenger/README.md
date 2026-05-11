# OpenClaw Facebook Messenger Plugin

Facebook Messenger channel plugin for OpenClaw via Meta Graph API v21.0.

## Verified status

This plugin has been locally verified for the OpenClaw side of the integration:

- the plugin loads through OpenClaw's plugin registry
- the full channel entry registers `/messenger/webhook`
- Meta webhook verification works (`GET` challenge echo)
- invalid webhook signatures are rejected with `403`
- valid signed webhook `POST` requests are accepted with `200 OK`

What is **not** verified by these local checks is the external Meta setup itself.
You still need a real Meta app, real page credentials, and a public webhook URL.

## Features

- Webhook-based inbound message handling
- HMAC-SHA256 webhook signature verification
- DM access policies: pairing (default), open, allowlist, disabled
- Text message send with 2000-char chunking
- Media attachment support (image, video, audio, file)
- Typing indicators (sender actions)
- Multi-account support (multiple Facebook Pages)
- Environment variable and config-based credential resolution

## Setup

## Official guides

- Messenger Platform getting started: `https://developers.facebook.com/documentation/business-messaging/messenger-platform/get-started`
- Graph API webhooks getting started: `https://developers.facebook.com/docs/graph-api/webhooks/getting-started`
- Facebook access tokens guide: `https://developers.facebook.com/documentation/facebook-login/guides/access-tokens`
- Tailscale Funnel guide: `https://tailscale.com/docs/features/tailscale-funnel`
- Tailscale Funnel examples: `https://tailscale.com/docs/reference/examples/funnel`

These are the main Meta docs you should follow alongside the OpenClaw config below.

## Activation model

Installing the plugin is not enough by itself.

OpenClaw only activates the Messenger channel when both are true:

- the plugin is enabled under `plugins.entries.messenger`
- `channels.messenger` exists and is configured

Without `channels.messenger`, the plugin can still be discovered by OpenClaw,
but the webhook route will not be active in your running gateway.

## Public webhook path

This workspace now includes a dedicated webhook-only proxy:

- script: `plugins/openclaw-messenger/scripts/messenger-webhook-proxy.mjs`
- systemd user service: `openclaw-messenger-webhook-proxy.service`
- local proxy port: `18890`

The proxy only exposes `GET` and `POST` on `/messenger/webhook` and returns
`404` for everything else. This is safer than exposing the whole OpenClaw
gateway directly.

### Tailscale status on this machine

The machine already has Tailscale installed and connected, but two extra steps
are still required before the webhook can be public:

1. Enable Funnel in the tailnet admin UI.
2. Allow this user to manage `tailscale serve` / `tailscale funnel`.

The exact links and commands are:

- Tailnet Funnel enable page: `https://login.tailscale.com/f/funnel?node=nWyoV6tDY511CNTRL`
- One-time local permission command:

```bash
sudo tailscale set --operator=$USER
```

- Then publish the proxy:

```bash
tailscale funnel --bg 18890
tailscale funnel status
```

After that, Tailscale will print the public HTTPS URL for this node. Use:

`https://<your-funnel-domain>/messenger/webhook`

as the Meta webhook callback URL.

### 1. Create a Facebook App

1. Go to [Meta Developer Console](https://developers.facebook.com/)
2. Create a new app (type: Business)
3. Add the **Messenger** product to your app
4. Go to **Messenger > Settings**

### 2. Generate a Page Access Token

1. In Messenger Settings, under **Access Tokens**, select your Facebook Page
2. Click **Generate Token**
3. Copy the token — this is your `pageAccessToken`

### 3. Configure Webhook

1. In Messenger Settings, under **Webhooks**, click **Subscribe to Events**
2. Set the **Callback URL** to your gateway's public URL + `/messenger/webhook`
   - Example: `https://your-domain.com/messenger/webhook`
   - For local dev, use ngrok or Tailscale Funnel
3. Set a **Verify Token** (any random string you choose)
4. Subscribe to these fields: `messages`, `messaging_postbacks`, `messaging_optins`

### 4. Get your App Secret

1. Go to **App Settings > Basic**
2. Copy the **App Secret**

### 5. Configure OpenClaw

Start with this safe staged config in `~/.openclaw/openclaw.json`:

```json
{
  "channels": {
    "messenger": {
      "enabled": false,
      "webhookPath": "/messenger/webhook",
      "dm": {
        "policy": "pairing"
      }
    }
  }
}
```

Then, once you have the real Meta credentials and public webhook, switch to:

```json
{
  "channels": {
    "messenger": {
      "enabled": true,
      "pageAccessToken": "YOUR_PAGE_ACCESS_TOKEN",
      "appSecret": "YOUR_APP_SECRET",
      "verifyToken": "YOUR_VERIFY_TOKEN",
      "webhookPath": "/messenger/webhook",
      "dm": {
        "policy": "pairing"
      }
    }
  }
}
```

Keeping `enabled: false` until real credentials are present avoids exposing a
webhook route without proper signature verification.

Or use environment variables:

```bash
export MESSENGER_PAGE_ACCESS_TOKEN="your-token"
export MESSENGER_APP_SECRET="your-secret"
export MESSENGER_VERIFY_TOKEN="your-verify-token"
```

The current implementation uses config values first and falls back to these
environment variables when the config values are absent.

### 6. Install the plugin

```bash
openclaw plugins install --link ./plugins/openclaw-messenger
```

`--link` is the right mode for local development on this machine.

### 7. Start the gateway

```bash
openclaw gateway
```

### 8. Test

Before adding the webhook to Meta, verify your local route works:

```bash
curl 'http://127.0.0.1:18789/messenger/webhook?hub.mode=subscribe&hub.verify_token=YOUR_VERIFY_TOKEN&hub.challenge=test123'
```

Expected response body: `test123`

Then test a bad signature:

```bash
curl -i -X POST 'http://127.0.0.1:18789/messenger/webhook' \
  -H 'Content-Type: application/json' \
  -H 'x-hub-signature-256: sha256=deadbeef' \
  --data '{"object":"page","entry":[]}'
```

Expected status: `403 Invalid signature`

You can also verify a valid signed request. A successful request should return
`200 OK`.

After that:

1. Send a message to your Facebook Page from a personal account
2. If using pairing policy, approve the pairing code:
   ```bash
   openclaw pairing approve messenger <code>
   ```
3. The agent should respond in Messenger

## Config reference

| Field | Type | Description |
|---|---|---|
| `enabled` | boolean | Enable/disable the channel |
| `pageAccessToken` | string | Facebook Page Access Token |
| `appSecret` | string | Facebook App Secret for signature verification |
| `verifyToken` | string | Webhook verify token |
| `webhookPath` | string | Webhook endpoint path (default: `/messenger/webhook`) |
| `dm.policy` | string | DM policy: `pairing`, `open`, `allowlist`, `disabled` |
| `dm.allowFrom` | string[] | Allowed sender IDs (when policy is `allowlist`) |
| `accounts` | object | Multi-account config (keyed by account ID) |
