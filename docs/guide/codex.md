# Connect Codex to contextkit

You need a contextkit API key (`ck_...`). Get one on [the contextkit website](https://contextkit-lime.vercel.app): **Get key**, sign in with GitHub, pick your repository and this agent as the client.

## Set up

Add to `~/.codex/config.toml`, replacing `ck_...` with your key:

```toml
[mcp_servers.contextkit]
url = "https://contextkit.onrender.com/mcp"
http_headers = { "Authorization" = "Bearer ck_..." }
```

Restart Codex. `/mcp` inside Codex lists the connected servers.

## Check the connection

Open a project and ask your agent to "load the project context". It should call `get_context` and show the briefing.

## Troubleshooting

- **First request times out:** the server sleeps when idle and can take up to a minute to wake. Reconnect once.
- **"API key is required":** the `Authorization` header is missing. Check it is spelled exactly `Authorization: Bearer ck_...`.
- **"Invalid API key":** the key is wrong or was revoked or rotated. Get a new one with **Rotate** in the website's key dialog.
- **Wrong project:** each key works for one project only, identified by its git remote URL (any form: https, SSH, with or without `.git`).

Keep your key out of files you commit. [Back to the README](../../README.md)
