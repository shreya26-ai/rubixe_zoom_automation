# Zoom Status Automation

A Python-based Zoom automation project for handling weekly status meetings, participant queueing, AI-based status extraction, and automated transcript processing. The project combines Zoom webhooks, queue orchestration, local speech prompts, transcript parsing, and AI summarization to convert a live meeting into structured weekly update records.

This repository is best understood as a prototype / automation playground: it contains a working webhook-driven pipeline plus several experimental variants and older scripts that were used during development.

## Overview

The workflow is designed around the following idea:

- A Zoom meeting starts.
- Participants join and are added to a speaking queue.
- An AI moderator calls each participant in turn using speech prompts.
- Zoom sends webhook events for joins, leaves, recording completion, and transcript completion.
- Recording files are downloaded and processed.
- Transcript/audio is transcribed and summarized.
- Batch IDs and weekly work notes are extracted.
- Results are stored in a database and optionally exported to Google Sheets or MongoDB.

## Core Features

- Zoom OAuth token retrieval via the Zoom account API
- FastAPI webhook server for Zoom events
- Real-time participant queue management
- AI voice announcements using text-to-speech
- Recording / transcript download from Zoom
- Audio transcription using Whisper
- LLM extraction of batch IDs and weekly updates
- Database persistence with SQLAlchemy
- Optional export to Google Sheets
- MongoDB storage for meeting summaries

## Project Structure

```text
Zoom_Automation/
├── .env                              # Local environment vars; keep secrets out of source control
├── README.md                         # Project documentation
├── app.py                            # Minimal FastAPI webhook stub
├── ai_extractor.py                   # Lightweight extractors / experimentation
├── ai_moderator.py                   # Audio-based moderator prototype
├── ai_queue_processor.py             # Queue / speaking coordination loop
├── ai_voice.py                       # gTTS-based local audio prompts
├── check_db.py                       # Reads saved meeting updates from SQL database
├── create_meeting.py                 # Creates Zoom meetings via the Zoom API
├── database.py                       # SQLAlchemy database configuration
├── get_participants.py               # Retrieves live participant list from Zoom APIs
├── groq_processor.py                 # LLM processing prototype using Groq
├── llm_extractor.py                  # JSON extraction logic for batch/work data
├── models.py                         # SQLAlchemy models for Participant and MeetingUpdate
├── mongo_db.py                       # MongoDB client setup
├── process_recordings.py             # Gemini-based transcript extraction experiments
├── queue_manager.py                  # In-memory participant queue logic
├── recording_downloader.py           # Downloads Zoom recordings and transcripts
├── requirements.txt                  # Python dependencies
├── test_*                            # Validation / experiment scripts
├── transcriber.py                    # Whisper transcription entrypoint
├── transcript_parser.py              # VTT transcript cleaning/parsing
├── transcript_processor.py           # Transcript processing utilities
├── webhook_server.py                 # Main FastAPI Zoom webhook server
├── zoom_auth.py                      # OAuth token generation for Zoom
├── zoom_meeting_controller.py        # Meeting end helper
├── unified_server*.py                # Legacy or alternate experimental server versions
├── ai_voice/                         # Audio asset folder
├── recordings/                      # Downloaded Zoom recordings/transcripts
├── temp_audio/                      # Temporary generated speech files
├── venv/                            # Virtual environment for local development
└── __pycache__/                     # Generated Python cache files
```

## Main Workflow

The project has a practical end-to-end flow similar to this:

1. Zoom sends webhook events to the FastAPI server.
2. `webhook_server.py` validates the webhook and handles events such as:
   - `meeting.participant_joined`
   - `meeting.participant_left`
   - `recording.completed`
   - `recording.transcript_completed`
3. Participants are queued using `queue_manager.py`.
4. `ai_queue_processor.py` triggers speech prompts when the meeting is ready.
5. When recordings complete, `recording_downloader.py` downloads Zoom files.
6. `transcriber.py` and `transcript_parser.py` extract clean text from audio/VTT data.
7. `llm_extractor.py` or other AI processors infer:
   - `batch_id`
   - `weekly_work`
   - confidence / structured summary data
8. Data is stored in SQLAlchemy models and/or MongoDB.
9. Optional export scripts push updates to Google Sheets.

## Environment Variables

Create a `.env` file in the project root. The exact keys vary by script, but the project expects values like:

```env
DATABASE_URL=postgresql://user:password@host:5432/zoom_ai
MONGO_URI=mongodb://localhost:27017
MONGO_URL=mongodb://localhost:27017
ZOOM_ACCOUNT_ID=your_zoom_account_id
ZOOM_CLIENT_ID=your_zoom_client_id
ZOOM_CLIENT_SECRET=your_zoom_client_secret
ZOOM_WEBHOOK_SECRET=your_zoom_webhook_secret
GOOGLE_SCRIPT_URL=https://script.google.com/macros/s/your_script_exec_url/exec
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key
EMAIL_USER=your_email_for_alerting
EMAIL_PASS=your_email_password
```

Important notes:

- Never commit real secrets to the repository.
- Some scripts rely on a PostgreSQL database while others use MongoDB.
- `ZOOM_WEBHOOK_SECRET` must match the secret configured in the Zoom App/Webhook settings.

## Dependencies

The project uses:

- FastAPI
- Uvicorn
- SQLAlchemy
- python-dotenv
- requests
- pymongo
- Whisper
- Groq / Ollama / Gemini depending on the processing script
- gTTS / playsound for voice prompts

Install the base dependencies with:

```bash
python -m venv venv
source venv/bin/activate   # Linux/macOS
# or
venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

## Running the Application

The main webhook server is `webhook_server.py`.

```bash
python webhook_server.py
```

or:

```bash
uvicorn webhook_server:app --host 0.0.0.0 --port 8000 --reload
```

This starts the FastAPI endpoint at:

- `POST /zoom/webhook`

The server validates Zoom webhook payloads and handles the automated meeting-processing cycle.

## Testing and Utility Scripts

Useful scripts in the repo include:

```bash
python check_db.py
python create_meeting.py
python get_participants.py
python test_sheets.py
python test_mongo.py
python test_token.py
```

These help with checking the database, creating meetings, validating Zoom tokens, exporting to Sheets, and testing connectivity.

## Data Model

The repo defines SQLAlchemy models in `models.py`:

- `Participant`
  - Tracks meeting participant joins and queue status
  - Fields include `name`, `meeting_id`, `status`, `attempts`, `zoom_user_id`, and `joined_at`

- `MeetingUpdate`
  - Stores extracted updates from transcripts
  - Fields include `name`, `batch_id`, `update`, and `created_at`

These models are paired with a database connection configured in `database.py`.

## Notes on Project Status

This repository is still in a prototype / experimentation phase. Some important realities:

- There are multiple server variants (`unified_server*.py`) and older experimental implementations.
- Some scripts duplicate functionality or rely on different AI providers.
- The project appears to be evolving toward a webhook-based Zoom status automation pipeline, but it is not yet a single clean production-ready package.
- The code can be used as a starting point for a more structured service architecture.

## Suggested Next Steps

For a cleaner production version, the project would benefit from:

- consolidating all server logic into one canonical application entrypoint
- standardizing environment configuration
- centralizing database and AI provider interfaces
- adding tests for webhook payload handling and transcript parsing
- separating legacy prototype files from active production code
- adding logging, monitoring, and retry handling for external API calls

## License

This repository does not currently include a project-specific license file. If you intend to share or deploy it publicly, add an appropriate open-source license before distribution.

## Contact / Usage

This project is designed for internal automation around Zoom-based team updates and status tracking. If you are using it in a real business workflow, ensure that:

- Zoom App credentials are configured correctly
- Webhook endpoints are secured with the proper validation secret
- Data retention and storage comply with your organization's privacy rules
- AI-generated summaries are reviewed before sharing externally
