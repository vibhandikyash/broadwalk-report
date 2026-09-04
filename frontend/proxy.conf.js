// Proxies /api to the FastAPI backend. Port: BACKEND_PORT env var, else BACKEND_PORT in ../.env, else 8000.
const fs = require('fs');
const path = require('path');

function backendPort() {
  if (process.env.BACKEND_PORT) return process.env.BACKEND_PORT;
  try {
    const env = fs.readFileSync(path.join(__dirname, '..', '.env'), 'utf8');
    const m = env.match(/^\s*BACKEND_PORT\s*=\s*(\d+)/m);
    if (m) return m[1];
  } catch (e) { /* no .env: use the default */ }
  return '8000';
}

module.exports = { '/api': { target: `http://localhost:${backendPort()}`, secure: false, changeOrigin: true } };
