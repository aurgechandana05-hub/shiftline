# Shiftline

**Carry the context. Not the whole conversation.**

Shiftline is a small, working incident-handoff web app for customer-support and on-call teams. Its central workflow is a sourced handoff for a synthetic Acme Logistics webhook escalation: carry forward the customer constraint, a failed workaround, a safe next check, and the operator-confirmed outcome.

The interface runs in two explicitly separate modes:

- **Local demo memory** is the no-configuration default. It stores its illustrative memories in a local SQLite database and is labeled “not Hindsight” throughout the UI. It is useful to try the interaction without API credentials.
- **Hindsight mode** sends retain and recall requests through the official `hindsight-client` Python SDK to the configured Hindsight server. The UI identifies the provider and bank. A failed remote operation is shown as an error; it does not fall back to local memory or report success.

All seeded customers and incident data are fictional. The current incident record is local app state; use the Hindsight retain/recall activity panel to distinguish that record from memories actually returned by Hindsight.

## Run locally on Windows

Python 3.9 or later is required. Node.js and a frontend build step are not required.

```powershell
cd C:\Users\lenovo\Desktop\shiftline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python server.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The default provider is **Local demo memory · not Hindsight**.

## Connect to Hindsight Cloud on Windows

1. Sign in or create an account at [Hindsight Cloud](https://ui.hindsight.vectorize.io/). The supplied hackathon problem statement advertises promo code `MEMHACK99` for Cloud credits, applied in the billing section after registration.
2. In Hindsight Cloud, provision/locate an API service and its API key using the information displayed in your account. Keep both on this computer; **do not paste the API key into chat or commit it to the repository**.
3. Run the local-only launcher:

```powershell
cd C:\Users\lenovo\Desktop\shiftline
.\run-live.ps1
```

The manual launcher prompts for your Hindsight Cloud API base URL and the memory-bank ID. Its key prompt is hidden. The secret is provided only to the running Shiftline server process; it is not saved to a `.env` or another file. It uses the dedicated `.venv-hindsight` environment with the official Python SDK.

If Shiftline is already open, close that local demo server before switching it to Hindsight mode. A prebuilt one-time `connect_cloud.py` bridge is also available for a connected Hindsight Cloud browser session. It verifies the Cloud API key, accepts a one-time browser-origin-restricted localhost handoff, starts the live app without writing the key to disk, and then exits.

If Windows blocks the script because of the current execution policy, run it for this invocation only with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-live.ps1
```

Shiftline checks the Hindsight API connection on startup. Confirm the live Hindsight indicator before demonstrating memory. Use **Load demo history** to create or configure the Shiftline bank and explicitly retain four fictional incident records in it. Then ask a question, open **Memory replay** to compare fresh-session and recalled context, or record a human-confirmed outcome.

Do not use a real customer or incident without explicit approval. Use a dedicated demo bank and the synthetic Acme Logistics scenario.

### Use a local/self-hosted Hindsight server instead

The live launcher is designed for HTTPS Cloud URLs. For a self-hosted API, use a Python 3.10+ environment and set `SHIFTLINE_MEMORY_MODE=hindsight`, `HINDSIGHT_API_URL=http://localhost:8888`, `HINDSIGHT_BANK_ID`, and (if needed) `HINDSIGHT_API_KEY` in that terminal before running `python server.py`.

When connected, use **Add context** to retain an operator-reviewed note, **Ask about this handoff** to recall and reflect on memories, **Memory replay** to compare the memory-off scenario with provider recall, and **Close the loop** to retain a human-confirmed outcome. The question flow first recalls evidence from Hindsight, then uses Hindsight `reflect()` when relevant memories were found. For the four-event demo narrative, use **Load demo history** shown in Hindsight mode. The seeded records are sent to the real configured Hindsight bank and can be retained more than once.

> See the current [Python SDK documentation](https://hindsight.vectorize.io/sdks/python) for deployment and API details. Shiftline creates or configures its Hindsight bank when you explicitly choose **Load demo history**; incident memories are sent only after an explicit **Add context**, **Load demo history**, or **Save to memory** action. Use a dedicated demo bank and synthetic data.

To use a separate persistent SQLite database, set `SHIFTLINE_DB_PATH` to an absolute path. To change the local web server port, set `PORT`.

## What is implemented

- Responsive incident view with customer impact, ownership, severity and sourced shift timeline.
- Next-shift brief separated into safe checks, failed approaches and customer constraints.
- Human-entered context and explicit outcome capture.
- Memory-on versus fresh-session memory-off comparison.
- Local demo SQLite memory and a live Hindsight SDK adapter for retain, recall, and reflect.
- Visible provider and retain/recall activity, with honest empty/error states.
- A Windows Cloud launcher that collects the API key through a hidden prompt and never writes it into the project.
- Tests for local retention, retrieval, taxonomy, and the Hindsight adapter using a fake SDK client.

The structured next-shift cards use retrieved evidence and transparent rules; they are not presented as a generated LLM summary. Hindsight `reflect()` powers the question flow in Hindsight mode. Ticket-system integrations, authentication, user/tenant administration, and production deployment are not implemented. The app does not claim to independently validate a memory or autonomously execute operational actions.

## Verify

```powershell
python -m unittest discover -s tests -v
```

## Live Hindsight recording

`Shiftline_Live_Hindsight_Walkthrough.mp4` is a narrated browser screen recording of the real app connected to Hindsight Cloud. It demonstrates explicit retention of the four synthetic handoff notes, an actual Hindsight recall and Reflect response, and the memory-on/off comparison. Matching captions are in `Shiftline_Live_Hindsight_Walkthrough.srt`. The narration explains the real-world purpose: carry a customer's constraints, failed steps, and uncertainty across on-call shifts so an incoming operator has a sourced starting point. The Acme Logistics incident is fictional and is clearly identified as synthetic throughout.

To create a fresh recording on Windows, first start Shiftline in live Hindsight mode, then install the recording-only packages into the same Python environment and run the capture script:

```powershell
cd C:\Users\lenovo\Desktop\shiftline
.\.venv-hindsight\Scripts\python.exe -m pip install -r .\requirements-recording.txt
.\.venv-hindsight\Scripts\python.exe .\generate_live_recording.py
```

The recorder checks the live Hindsight health endpoint before it starts and requires a successful live Reflect answer and memory comparison. It uses installed Microsoft Edge, the built-in Windows speech voice, and FFmpeg to capture the actual app and package narration. It uses the four synthetic records already retained in Hindsight; rerunning it does not seed the bank again. It does not contain or request an API key; keep the live app running while it records.

## Illustrative demo video

The [720p narrated product walkthrough](./Shiftline_Demo_Walkthrough.mp4) is about 2 minutes 24 seconds. It includes subtitles at [Shiftline_Demo_Walkthrough.srt](./Shiftline_Demo_Walkthrough.srt), covers the seeded fictional escalation and memory-on/off comparison, and explicitly discloses that the rendered walkthrough uses local demo memory rather than a live Hindsight instance. The on-screen app views are illustrative recreations of the interface, not a live screen recording. Do not present it as proof of a live Hindsight call; generate a separate recording after Cloud is connected and the retain/recall/reflect interactions are verified.

To regenerate it on Windows, install the renderer dependencies and run the generator. Narration uses the installed **Microsoft Zira Desktop** Windows speech voice.

```powershell
python -m pip install Pillow imageio imageio-ffmpeg
python generate_demo_video.py
```

## Hindsight memory boundary

The app keeps the current incident view and operator timeline in SQLite. `MemoryService` is the only boundary for persistent recall/retention. In Hindsight mode it calls `retain` with incident context and metadata, then calls `recall` for a fresh handoff. Hindsight is configured server-side; the SDK is imported only when that provider is selected. Local demo memory is a separate provider and is never described as Hindsight.

## Before a public pilot

Add authentication and authorization, separate and verify memory banks per tenant, apply a retention/deletion policy, protect the service with HTTPS, and review all sources and privacy requirements. This prototype binds only to `127.0.0.1` and is not production-ready.

## Project links

- [Hindsight documentation](https://hindsight.vectorize.io/)
- [Hindsight Python SDK](https://hindsight.vectorize.io/sdks/python)
- [Vectorize agent memory](https://vectorize.io/what-is-agent-memory)
