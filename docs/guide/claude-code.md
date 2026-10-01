# Connect Claude Code to contextkit

You need a contextkit API key (`ck_...`). Ask your contextkit admin for one.

## Set up

Run once in your terminal, replacing `ck_...` with your key:

```bash
claude mcp add --transport http contextkit https://contextkit.onrender.com/mcp \
  --header "Authorization: Bearer ck_..."
```

Add `--scope user` to make contextkit available in every project, not only the current one.

Check it with `claude mcp list`; `contextkit` should show as connected. Inside Claude Code, `/mcp` shows the server and its tools.

## Check the connection

Open a project and ask your agent to "load the project context". It should call `get_context` and show the briefing.

## Troubleshooting

- **First request times out:** the server sleeps when idle and can take up to a minute to wake. Reconnect once.
- **"API key is required":** the `Authorization` header is missing. Check it is spelled exactly `Authorization: Bearer ck_...`.
- **"Invalid API key":** the key is wrong or was revoked or rotated. Ask your contextkit admin for a new one.
- **Wrong project:** each key works for one project only, identified by its git remote URL.

Keep your key out of files you commit. [Back to the README](../../README.md)
