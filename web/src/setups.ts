// Connect texts for each supported agent. `ck_...` stands for the user's API key.

const MCP_URL = 'https://contextkit.onrender.com/mcp'
const KEY_PLACEHOLDER = 'ck_...'
const AUTH_HEADER = `Authorization: Bearer ${KEY_PLACEHOLDER}`

export interface AgentSetup {
  agent: string
  /** File name of the agent's guide in docs/guide/, without `.md`. */
  guide: string
  /** A terminal command, or a snippet to add to a config file. */
  kind: 'command' | 'config'
  /** Where a config snippet goes. */
  file?: string
  text: string
}

export const SETUPS: AgentSetup[] = [
  {
    agent: 'Claude Code',
    guide: 'claude-code',
    kind: 'command',
    text: `claude mcp add --transport http contextkit ${MCP_URL} --header "${AUTH_HEADER}"`,
  },
  {
    agent: 'Gemini CLI',
    guide: 'gemini-cli',
    kind: 'command',
    text: `gemini mcp add --transport http contextkit ${MCP_URL} --header "${AUTH_HEADER}"`,
  },
  {
    agent: 'VS Code (Copilot)',
    guide: 'vscode',
    kind: 'command',
    text: `code --add-mcp '{"name":"contextkit","type":"http","url":"${MCP_URL}","headers":{"Authorization":"Bearer ck_..."}}'`,
  },
  {
    agent: 'Cursor',
    guide: 'cursor',
    kind: 'config',
    file: '~/.cursor/mcp.json',
    text: `{
  "mcpServers": {
    "contextkit": {
      "url": "${MCP_URL}",
      "headers": { "Authorization": "Bearer ck_..." }
    }
  }
}`,
  },
  {
    agent: 'Windsurf',
    guide: 'windsurf',
    kind: 'config',
    file: '~/.codeium/windsurf/mcp_config.json',
    text: `{
  "mcpServers": {
    "contextkit": {
      "serverUrl": "${MCP_URL}",
      "headers": { "Authorization": "Bearer ck_..." }
    }
  }
}`,
  },
  {
    agent: 'Codex',
    guide: 'codex',
    kind: 'config',
    file: '~/.codex/config.toml',
    text: `[mcp_servers.contextkit]
url = "${MCP_URL}"
http_headers = { "Authorization" = "Bearer ck_..." }`,
  },
]

/** The setup text with the placeholder replaced by a real key. */
export function setupWithKey(setup: AgentSetup, apiKey: string): string {
  return setup.text.replaceAll(KEY_PLACEHOLDER, apiKey)
}
