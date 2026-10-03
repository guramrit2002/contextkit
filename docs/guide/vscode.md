# Connect VS Code (GitHub Copilot) to contextkit

You need a contextkit API key (`ck_...`). Get one on [the contextkit website](https://contextkit-lime.vercel.app): **Get key**, sign in with GitHub, pick your repository and this agent as the client.

## Set up

Run once in your terminal, replacing `ck_...` with your key:

```bash
code --add-mcp '{"name":"contextkit","type":"http","url":"https://contextkit.onrender.com/mcp","headers":{"Authorization":"Bearer ck_..."}}'
```

Open Copilot Chat in **Agent** mode and click the tools icon; the contextkit tools should be listed.

## Check the connection

Open a project and ask your agent to "load the project context". It should call `get_context` and show the briefing.

## Troubleshooting

- **First request times out:** the server sleeps when idle and can take up to a minute to wake. Reconnect once.
- **"API key is required":** the `Authorization` header is missing. Check it is spelled exactly `Authorization: Bearer ck_...`.
- **"Invalid API key":** the key is wrong or was revoked or rotated. Get a new one with **Rotate** in the website's key dialog.
- **Wrong project:** each key works for one project only, identified by its git remote URL (any form: https, SSH, with or without `.git`).

Keep your key out of files you commit. [Back to the README](../../README.md)
