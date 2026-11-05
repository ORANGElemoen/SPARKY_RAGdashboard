# Moving Sparky to a new machine

Git holds the code. Everything private lives in a backup zip made by
`scripts/backup_sparky.py`. You need both.

## Back up

```powershell
.\.venv\Scripts\python.exe scripts\backup_sparky.py
```

This is safe while the server is running. It writes
`backups/sparky_backup_<date>_<time>.zip`. Copy that zip off the laptop, for
example to your Google Drive, and make a new one after changing documents,
voice lines or faces.

The zip holds the question log and uploaded files, so never commit it. The
repository is public. `backups/` is gitignored for this reason.

| In the zip | Not in the zip (get it again) |
|---|---|
| `data/rag_database.db`: documents, embeddings, device keys, question log | Ollama models: `ollama pull qwen3.5:4b` |
| `data/storage/`: uploaded PDFs | Whisper and embedding models: download on first use, so go online once |
| `data/studio/`: voice lines and faces | Stock Piper voice: only needed if the Sparky voice is missing |
| `data/piper_voices/en_US-sparky-medium.onnx`: Sparky's voice | Voice training files: `latest.ckpt`, `reference.wav` etc. stay in `MyDrive/sparky_voice/` |
| `.env`, if there is one | |
| `firmware/sparky/local_config.h`: the addresses built into the firmware | |

## Set up the new machine

1. Install Git, Python, Ollama, ffmpeg and (for firmware work) Arduino CLI.
   ```powershell
   winget install --id Git.Git --exact
   winget install --id Python.Python.3.14 --exact
   winget install --id Ollama.Ollama --exact
   winget install --id Gyan.FFmpeg --exact
   winget install --id ArduinoSA.CLI --exact
   ```
2. Get the code and its Python packages.
   ```powershell
   git clone https://github.com/ORANGElemoen/SPARKY_RAGdashboard.git
   cd SPARKY_RAGdashboard
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r deployment\requirements\voice_requirements.txt
   ```
3. Pull the model: `ollama pull qwen3.5:4b`
4. Unzip the backup into the `SPARKY_RAGdashboard` folder, keeping its folder
   paths, so that `data\rag_database.db` ends up in place. Do this with the server
   stopped.
5. Start the server with `scripts\start_sparky_server.bat`.

## Check it worked

- The document list at `/admin/documents/management` shows your sheets.
- Sparky Studio at `/admin/studio/view` shows your voice lines and faces.
- A voice question comes back in Sparky's voice. The server log says
  `Loading Piper voice: en_US-sparky-medium`.

`documents.file_path` in the database is an absolute path. If the repo is in a
different folder on the new machine, answers still work because the text is in the
database, but downloading an original PDF returns a 404. Restore to
`C:\Users\chris\SPARKY_RAGdashboard` to avoid this, or upload the PDFs again.

## Reconnect internet access

The ngrok token and dashboard login are not in the backup. They're stored in
`%LOCALAPPDATA%\ngrok` on each machine. To set them up again:

1. Install ngrok from the Microsoft Store. Windows Defender may block a direct
   download. `winget install --id 9MVS1J51GMK6 --source msstore`
2. Run `scripts\setup_ngrok.bat`.

`scripts\start_sparky_server.bat` then opens the tunnel in its own window. Your
address stays the same because it belongs to your ngrok account, and it's shown
on the window's "Forwarding" line.

## Reconnect the board

The board keeps its device key, and restoring the database keeps that key valid.
The server address will change if the new machine has a different address: hold
Sparky's button while switching on, then enter the new one on the setup page.

If the board needs flashing, install the ESP32 core and libraries first, then see
`firmware/sparky/README.md`. Always use the `PartitionScheme=no_ota` board option shown
there, because any other layout wipes the voice lines.

```powershell
arduino-cli core install esp32:esp32
arduino-cli lib install WiFiManager ArduinoJson MD_MAX72XX
```

On boards where the upload stops at `Wrong boot mode detected (0x13)`, hold BOOT
until the upload has finished.
