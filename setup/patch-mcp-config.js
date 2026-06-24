const fs = require('fs');
const path = 'C:/Users/jackw/.claude.json';
const projectKey = 'C:/Users/jackw/Desktop/42';

const c = JSON.parse(fs.readFileSync(path, 'utf8'));
if (!c.projects[projectKey]) {
  console.error('ERROR: project entry missing for', projectKey);
  process.exit(1);
}

c.projects[projectKey].mcpServers = {
  tradingview: {
    type: 'stdio',
    command: 'node',
    args: ['C:/Users/jackw/Desktop/SwjshAlgoKnife/mcp-servers/tradingview-mcp/src/server.js'],
    env: {}
  },
  alpaca: {
    type: 'stdio',
    command: 'uvx',
    args: ['alpaca-mcp-server'],
    env: {
      // Keys must come from .mcp.json (gitignored) — never commit real values here.
      // See .mcp.json.example for the expected structure.
      ALPACA_API_KEY: process.env.ALPACA_API_KEY || '<YOUR_ALPACA_API_KEY>',
      ALPACA_SECRET_KEY: process.env.ALPACA_SECRET_KEY || '<YOUR_ALPACA_SECRET_KEY>',
      ALPACA_PAPER_TRADE: 'true',
      ALPACA_BASE_URL: 'https://paper-api.alpaca.markets'
    }
  }
};

const tmp = path + '.tmp';
fs.writeFileSync(tmp, JSON.stringify(c, null, 2), 'utf8');
fs.renameSync(tmp, path);

const verify = JSON.parse(fs.readFileSync(path, 'utf8'));
console.log('OK — 42.mcpServers now:');
console.log(JSON.stringify(verify.projects[projectKey].mcpServers, null, 2));
