# Setup on a new machine with a hosted LLM (no local model)

This guide sets the project up on a machine without Ollama, using a hosted
OpenAI-compatible API (for example Mistral or OpenAI) with your own API URL and key.

**No code changes are needed.** The model is chosen only through settings: install the
tools, create one `.env` file with the API URL and key, and start the services. The key
only ever goes into `.env`, which git ignores.

The project runs on **Python 3.13.2** (pinned in `.python-version`).

Commands below are for **Windows PowerShell**; Linux/macOS equivalents are given where they differ.

---

## 1. Install the prerequisites

| Tool | Notes |
|---|---|
| Git | To clone the repository |
| Python **3.13.2** | From [python.org](https://www.python.org/downloads/windows/). Needed for the pip route; the uv route can also download it |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Recommended installer. Optional if you use the pip route in step 3B |
| Node.js 20 or newer | For the dashboard |

No Ollama is needed.

## 2. Clone the repository

```powershell
git clone https://github.com/Jotiba-Patil/ai-powered-dr-readiness-agent.git
cd ai-powered-dr-readiness-agent
```

## 3. Install the backend (pick 3A or 3B)

### 3A. With uv (normal networks)

```powershell
uv sync
```

`uv` uses an installed Python 3.13.2, or downloads it. If this fails with
**"invalid peer certificate"**, your network inspects HTTPS traffic: see
[Corporate networks and certificate errors](#corporate-networks-and-certificate-errors),
or use 3B.

### 3B. With pip (when uv is blocked by the network)

pip uses the Windows certificate store, where company certificates are installed, so it
often works where `uv` does not.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version                     # must print Python 3.13.2
```

Install the exact versions from the lock file. `uv export` only reads `uv.lock` and needs
no internet:

```powershell
uv export --frozen --all-groups --no-emit-project --no-hashes --format requirements-txt -o requirements.txt
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
```

If `uv` is not installed at all, install the project with its dependencies directly
(pip then picks the newest compatible versions instead of the locked ones, and the test
tools are not included):

```powershell
python -m pip install -e .
```

Keep the virtual environment active (`.\.venv\Scripts\Activate.ps1`) in every terminal
you use for the backend. `requirements.txt` is a generated file; do not commit it.

## 4. Install the dashboard

```powershell
cd frontend
npm ci
cd ..
```

If this fails with `UNABLE_TO_GET_ISSUER_CERT_LOCALLY` or `SELF_SIGNED_CERT_IN_CHAIN`, see
[Corporate networks and certificate errors](#corporate-networks-and-certificate-errors).

## 5. Create `.env` in the project root

```powershell
copy .env.example .env               # Linux/macOS: cp .env.example .env
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
| `LLM_TIMEOUT_SECONDS` | `120` is plenty for a hosted API |

> **Important:** without a `.env`, the app defaults to `ollama`, cannot reach it, and falls
> back to rule-based reports only.

### Optional: allow runbook execution

Add to the same `.env`:

```ini
EXECUTION_ENABLED=true
EXECUTION_ALLOW_LIVE=true
EXECUTION_AI_PROPOSALS=true
```

- Execution only ever calls the bundled mock MCP server.
- With AI proposals on, creating a run asks the model to propose a call for each step
  without a `Tool:` annotation. That uses your API quota, but it is fast with a hosted model.
  `EXECUTION_AI_PROPOSALS=false` makes such steps manual immediately.

## 6. Start both services

Run each command from the project root, in its own terminal. The API reads `.env` from the
folder it is started in.

| | uv route (3A) | pip route (3B, venv active) |
|---|---|---|
| API | `uv run poe dev-api` | `python -m dr_agent.api` |
| Dashboard | `uv run poe dev-ui` | `npm --prefix frontend run dev` |

Then open the dashboard at http://localhost:5173. The API is at http://127.0.0.1:8000
(interactive docs at http://127.0.0.1:8000/docs).

## 7. Check that the model is being used

1. Health check (should return `{"status":"ok",...}`):

   ```powershell
   curl.exe http://127.0.0.1:8000/api/v1/health
   ```

2. One analysis from the command line (`uv run dr-agent ...` on the uv route, just
   `dr-agent ...` with the venv active on the pip route):

   ```powershell
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
| Certificate or SSL error | See the next section |

3. Optional, the full test suite (fake model: needs neither the key nor the network):
   `uv run poe test` (uv route) or `pytest` (pip route, venv active).

---

## Corporate networks and certificate errors

Some company networks (proxy, VPN or antivirus) inspect HTTPS traffic and re-sign it with a
company root certificate. Windows and browsers trust it; some tools do not, and fail with
"invalid peer certificate", `CERTIFICATE_VERIFY_FAILED` or `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`.

First get the company root certificate as a Base-64 `.pem`/`.crt` file: from IT, or in the
browser via the padlock → certificate → the top certificate of the chain → export as Base-64.
The examples use `C:\certs\company-root-ca.pem`.

| Tool | Fix |
|---|---|
| **uv** (`uv sync`, Python download) | `$env:UV_NATIVE_TLS = "true"` (uses the Windows certificate store). If that is not enough: `$env:SSL_CERT_FILE = "C:\certs\company-root-ca.pem"`. Or use the pip route (3B) |
| **pip** | Usually works as is. Otherwise: `python -m pip install --cert C:\certs\company-root-ca.pem ...` |
| **npm** (`npm ci`) | `npm config set cafile "C:\certs\company-root-ca.pem"`, or with Node 22.15+/23.8+: `$env:NODE_OPTIONS = "--use-system-ca"` |
| **The app's calls to your LLM API** | Set `SSL_CERT_FILE` as a real environment variable **before** starting the API: `$env:SSL_CERT_FILE = "C:\certs\company-root-ca.pem"`. It does **not** work inside `.env` |
| **Behind an explicit proxy** | Also set `$env:HTTPS_PROXY = "http://proxy.company.com:8080"` (again as an environment variable, not in `.env`) |

To make an environment variable permanent for your user, use `setx NAME value` and open a
new terminal. Linux/macOS: `export NAME=value`.

Do not switch certificate checks off (`--allow-insecure-host`, `--trusted-host`,
`strict-ssl=false`): anyone on the network could then tamper with what you install.

---

## Alternative: Docker Compose

1. Install Git and Docker Desktop (or Docker Engine with Compose v2), and clone as in step 2.
   You do not need Python, uv or Node.
2. Create `.env` as in step 5. Compose already defaults to `openai_compatible` with Mistral;
   without a key the API will not start.
3. Optionally add `EXECUTION_ENABLED=true` and `EXECUTION_ALLOW_LIVE=true`.
4. Run `docker compose up --build`.
5. Open the dashboard at http://localhost:8080 (the API is at http://localhost:8000). The
   dashboard reaches the API through its own web server, so the frontend needs no settings.
   Stored analyses are kept in the `dr-agent-data` Docker volume.

On a network that re-signs HTTPS, image builds fail the same way: the company certificate
must then be added to the images. Docker has not yet been run on the project's original
machine, so this is the less-tested path.

---

## Opening the dashboard from another computer

By default everything listens on localhost only. To reach it over the network (not Docker):

- in `.env`: `API_HOST=0.0.0.0` and `CORS_ORIGINS=http://<this-machine-ip>:5173`
- in `frontend/.env` (copy `frontend/.env.example`): `VITE_API_BASE_URL=http://<this-machine-ip>:8000`
- start the dashboard with `npm --prefix frontend run dev -- --host`

The API has no login, so only do this on a trusted network.

---

## Good to know

- **Fresh history:** stored analyses (`dr-agent.db`) are not in the repository, so the
  History tab and the knowledge base start empty on the new machine.
- **Data leaves the machine:** runbook contents and dependency health are sent to your API
  provider. Make sure that is acceptable for your runbooks.
- **Windows only:** if a `uv run poe ...` command fails with
  `uv trampoline failed to canonicalize script path`, run `uv sync --reinstall`.
- **Keep the key out of git:** never commit `.env` (already in `.gitignore`).
