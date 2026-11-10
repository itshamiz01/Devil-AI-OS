# AUTONOMUS — Windows Run Guide

*Run the complete AUTONOMUS system (Devil AI OS) on your own Windows PC, sign in for the first time, secure it, and use it from your phone on your home Wi-Fi.*

Everything below is taken from the system as built — the start scripts, the configuration and the first-start behaviour were all read from the actual code. One honest note before you begin: AUTONOMUS has been built and fully tested on Linux, but **this will be its first run on Windows**. The steps are exact; if anything errors, copy the error text to Muse and it will be fixed — that first run is the pilot the whole programme has been waiting for.

---

## What you need

1. **The system package:** `AUTONOMUS-Expansion-F06-Staging.zip` (the file Muse prepared for you — it contains the complete system, including the ready-built Command Center, so no extra build tools are needed).
   *Alternative:* download the ZIP of the `Devil-AI-OS` repo from your GitHub — it contains the same code, the ready-built Command Center, and this guide (in `docs`). Only the three PNG app-icon files are missing from the GitHub copy (a platform limit on how the files were uploaded); they are not needed to run the system — they only serve the phone-install of the Vercel copy.
2. **Python 3.11 or newer** (free, from python.org — Step 1 below).
3. About **15–20 minutes** for the first run. Later starts take seconds.

Your PC (Core i7, 16 GB RAM) is more than enough.

---

## Step 1 — Install Python

1. Go to **python.org → Downloads → Windows** and install the latest Python 3 (3.11 or newer).
2. On the installer's first screen, tick **"Add python.exe to PATH"** before clicking Install. This matters — without it, nothing below works.
3. Check it worked: open **PowerShell** (Start menu → type `PowerShell`) and run:

   ```
   python --version
   ```

   You should see something like `Python 3.12.x`.

## Step 2 — Unpack the system

1. Right-click `AUTONOMUS-Expansion-F06-Staging.zip` → **Extract All**.
2. Extract it somewhere simple, for example `C:\` — you will get a folder:

   ```
   C:\autonomus-ai-os
   ```

   (Inside it: `backend`, `frontend`, `scripts`, `docs`.)

## Step 3 — Set your owner password (do this BEFORE the first start)

The system has no built-in password — by design, **you** choose it, and it is locked in the first time the system starts. Choose one you will not forget; changing it later is done inside the app, not by editing this file again.

1. Open the folder `C:\autonomus-ai-os\backend`.
2. Create a new text file there named exactly:

   ```
   .env
   ```

   (In Notepad, when saving, set "Save as type" to **All Files** so it doesn't become `.env.txt`.)
3. Put exactly one line in it:

   ```
   AUTONOMUS_ADMIN_PASSWORD=your-chosen-password
   ```

4. Save and close.

Your username is fixed: **owner**.

> If the system is ever started *without* this file, it runs locked — no password exists and every sign-in is refused. The fix is in Troubleshooting below.

## Step 4 — (Optional) Check your machine

From PowerShell, in the `C:\autonomus-ai-os` folder:

```
powershell -ExecutionPolicy Bypass -File .\scripts\validate_environment.ps1
```

It checks Python and the other tools and reports OK/MISSING for each. (The `-ExecutionPolicy Bypass` part is needed because Windows blocks downloaded scripts by default — it applies to this one run only.)

## Step 5 — Start AUTONOMUS

From PowerShell, in the `C:\autonomus-ai-os` folder:

```
powershell -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1
```

**First start takes a few minutes.** The script automatically:

- creates the system's private Python environment,
- installs the libraries it needs (one-time download),
- creates the database and runs all migrations,
- stores your password as a secure hash,
- starts the engine on `http://127.0.0.1:8000`.

When you see a line like **`Uvicorn running on http://127.0.0.1:8000`**, it is live. **Leave this window open** — closing it (or pressing Ctrl+C) stops the system.

## Step 6 — Sign in

1. In your browser on the PC, open:

   ```
   http://127.0.0.1:8000/app
   ```

2. Sign in:
   - **Username:** `owner`
   - **Password:** the one you set in Step 3.

You're in the Command Center — the same interface as the website, now with the real engine behind it.

## Step 7 — Secure your account (first sign-in, 3 minutes)

In the **Security** view:

1. **Enrol this device** — register the PC, give it a name, and mark it **trusted**. (The system binds sign-ins to known devices.)
2. **Generate your MFA recovery codes** — a set of one-time codes. Save them somewhere safe outside the PC (a photo in a private place, a note in your password manager). They are your way back in if you ever lose access.
3. Done — the account is properly yours now.

## Step 8 — Use it from your phone (same Wi-Fi)

The normal start (Step 5) listens only on the PC itself. To reach it from your phone:

1. Stop the running system (Ctrl+C in its PowerShell window).
2. Start it in phone-reachable mode — from the `C:\autonomus-ai-os\backend` folder in PowerShell:

   ```
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

3. If Windows Firewall asks, click **Allow** for private networks.
4. Find the PC's address: in PowerShell run `ipconfig` and note the **IPv4 Address** (it looks like `192.168.1.20`).
5. On your phone, connected to the **same Wi-Fi**, open in Chrome:

   ```
   http://192.168.1.20:8000/app
   ```

   (with your PC's actual address). Sign in as **owner**. If the Security view asks you to enrol the phone as a device, do it and mark it trusted.

**Safety:** this works only inside your home network — which is exactly how it should be. Do **not** set up port forwarding or expose this address to the internet.

## Stopping the system

- Ctrl+C in the PowerShell window where it runs, or run `scripts\stop_backend.ps1`.
- Your data lives in `C:\autonomus-ai-os\backend\data` — it survives restarts. Back that folder up if the system starts holding things you value.

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` is not recognised | Python wasn't added to PATH. Reinstall Python and tick **"Add python.exe to PATH"**. |
| The script is blocked / "cannot be loaded because running scripts is disabled" | Use the exact command in Step 5 — the `-ExecutionPolicy Bypass` form. |
| Sign-in is refused even with the right password | The system was probably started once *before* the `.env` file existed, so no password was stored. Stop it, delete the folder `C:\autonomus-ai-os\backend\data` (this wipes the fresh, still-empty database — only do this on a brand-new install), confirm `.env` is in place, and start again. |
| "Port 8000 is already in use" | Something else is using it, or an old copy is still running. Close the old window, or set a different port: `$env:AUTONOMUS_PORT="8001"` before Step 5 (and use 8001 in the addresses). |
| The page at `/app` is blank or 404 | The built Command Center is missing — this happens if `frontend\dist` was deleted. Restore it by re-downloading the package, or install Node.js (18+), then in the `frontend` folder run `npm install` and `npm run build`, then restart the backend. |
| The phone can't connect | PC and phone must be on the same Wi-Fi; the system must be started with the Step 8 command; allow Python through the firewall when asked. |
| An error you don't recognise | Copy the full text from the PowerShell window and send it to Muse. |

## What to expect once you're in

- **Everything structural works:** the Command Center, approvals, businesses, finance ledger, survival engine, memory, security, operations, knowledge & files.
- **No AI model is connected yet.** The built-in engines are deterministic and work as-is; connecting a local AI model (Ollama) is a separate, later step — on your machine it will run on CPU, which suits smaller models.
- **Integrations** (Stripe, YouTube, etc.) honestly show as *requires configuration* until you connect them one at a time — nothing is faked.
- From here, the pilot path is: connect one model, connect one integration, and put **one real opportunity** through the full governed path — that's the moment AUTONOMUS stops being a build and starts being a business.

*Guide written for the F06 build of AUTONOMUS (backend 1113 tests, frontend 66 tests — READY FOR CONTROLLED PILOT).*
