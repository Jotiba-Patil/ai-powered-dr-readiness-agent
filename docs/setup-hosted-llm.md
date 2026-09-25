# Setup on a new machine with a hosted LLM (no local model)

This guide sets the project up on a machine without Ollama, using a hosted
OpenAI-compatible API (for example Mistral or OpenAI) with your own API URL and key.

**No code changes are needed.** The model is chosen only through settings: install
the tools, create one `.env` file with the API URL and key, and start the services.
The key only ever goes into `.env`, which git ignores.

Pick one of the two ways to run it: **Option A** (directly, for development) or
**Option B** (Docker Compose).

---

## Option A: run directly (development setup)

### 1. Install the prerequisites

- Git
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (installs Python 3.12 for you)
- Node.js 20 or newer
- No Ollama is needed.

### 2. Clone and install

```bash
git clone https://github.com/Jotiba-Patil/ai-powered-dr-readiness-agent.git
cd ai-powered-dr-readiness-agent
uv sync
cd frontend && npm ci && cd ..
```

### 3. Create `.env` in the project root

Copy the template:

```bash
copy .env.example .env      # Windows
cp .env.example .env        # Linux / macOS
```

Then edit these lines in `.env`:

```ini
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://your-provider.example.com/v1
LLM_MODEL=your-model-name
LLM_API_KEY=your-key-here
LLM_RESPONSE_FORMAT=json_schema
LLM_TIMEOUT_SECONDS=120
```

| Setting | What to put there |
|---|---|
| `LLM_BASE_URL` | The API root **including the version path** (usually `/v1`). The app adds `/chat/completions` itself. Examples: `https://api.mistral.ai/v1`, `https://api.openai.com/v1` |
| `LLM_MODEL` | Your provider's model name, for example `mistral-small-latest` or `gpt-4o-mini` |
| `LLM_API_KEY` | Your API key |
| `LLM_RESPONSE_FORMAT` | Keep `json_schema` for OpenAI, Mistral or vLLM. If your provider rejects it, use `json_object` |
| `LLM_TIMEOUT_SECONDS` | `120` is plenty for a hosted API (the default `300` was for a slow CPU model) |

> **Important:** without a `.env`, the code defaults to `ollama`, cannot reach it, and falls back to rule-based reports only.

### 4. Optional: allow runbook execution

Add to the same `.env`:

```ini
EXECUTION_ENABLED=true
EXECUTION_ALLOW_LIVE=true
EXECUTION_AI_PROPOSALS=true
```

- Execution only ever calls the bundled mock MCP server.
- With AI proposals on, creating a run asks the model to propose a call for each step
  without a `Tool:` annotation. That uses your API quota, but it is fast with a hosted model.

### 5. Start both services

From the project root, in two terminals:

```bash
uv run poe dev-api      # API on http://127.0.0.1:8000
uv run poe dev-ui       # dashboard on http://localhost:5173
```

Start the API from the project root, because that is where it reads `.env`.
Then open http://localhost:5173.

---

## Option B: Docker Compose

1. Install Git and Docker Desktop (or Docker Engine with Compose v2), then clone as in
   Option A, step 2. You do not need uv or Node.
2. Create `.env` in the project root with the same `LLM_*` lines as Option A, step 3.
   Compose already defaults to `openai_compatible` with Mistral; without a key the API
   will not start.
3. Optionally add `EXECUTION_ENABLED=true` and `EXECUTION_ALLOW_LIVE=true`.
4. Run:

   ```bash
   docker compose up --build
   ```

5. Open the dashboard at http://localhost:8080. The API is at http://localhost:8000.
   - The dashboard reaches the API through its own web server, so the frontend needs no settings.
   - Stored analyses are kept in the `dr-agent-data` Docker volume.

> Docker has not yet been run on the project's original machine, so this is the less-tested path.

---

## Only if you open the dashboard from another computer

By default everything listens on localhost only. To reach it over the network with Option A:

- in `.env`:

  ```ini
  API_HOST=0.0.0.0
  CORS_ORIGINS=http://<this-machine-ip>:5173
  ```

- in `frontend/.env` (copy `frontend/.env.example`):

  ```ini
  VITE_API_BASE_URL=http://<this-machine-ip>:8000
  ```

- start the UI with `npm --prefix frontend run dev -- --host`.

The API has no login, so only do this on a trusted network.

---

## Check that the model is being used

1. Health check:

   ```bash
   curl http://127.0.0.1:8000/api/v1/health
   ```

   It should return `{"status":"ok",...}`.

2. Quick analysis from the command line:

   ```bash
   uv run dr-agent analyze -r mock-data/runbooks/estimate-service.md -i mock-data/inventories/healthy.json
   ```

   A normal report with an AI-written summary means it works. A yellow
   "AI analysis unavailable: …" line means the model call failed; the text after it says why.

| Message | Fix |
|---|---|
| `CONFIG_ERROR … LLM_API_KEY: is required` | The key is missing from `.env` |
| 401 / 403 from the provider | The key is wrong or has no access to that model |
| 404 | `LLM_BASE_URL` is missing `/v1`, or `LLM_MODEL` is misspelled |
| Schema or `response_format` error | Set `LLM_RESPONSE_FORMAT=json_object` |

3. Full test suite (uses a fake model, so it needs neither the key nor the network):

   ```bash
   uv run poe test
   ```

---

## Good to know

- **Fresh history:** stored analyses (`dr-agent.db`) are not in the repository, so the
  History tab and the knowledge base start empty on the new machine.
- **Data leaves the machine:** runbook contents and dependency health are sent to your
  API provider. Make sure that is acceptable for your runbooks.
- **Windows only:** if a `uv run poe …` command fails with
  `uv trampoline failed to canonicalize script path`, run `uv sync --reinstall`.
- **Keep the key out of git:** never commit `.env`. It is already in `.gitignore`.
