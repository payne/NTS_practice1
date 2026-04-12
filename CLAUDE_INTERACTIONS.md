# Claude Code Interactions — N0LJD / NTS Message Scorer

**Working directory:** `/home/mpayne/git/N0LJD`
**Date:** 2026-04-11

---

## Session 1 — Application Build
**Session ID:** `b950240d-5b35-472c-bf42-46ebeb9d1a7d`
**Timestamp:** 2026-04-11 16:16 UTC

### User Prompt

> Create a web application using python sqlite that allows operators to enter a NTS message that has been sent to them via the radio and then scores it for accuracy against the original that is stored in the database.

### Claude Response Summary

Claude built a complete Flask web application for NTS (National Traffic System) radiogram scoring. The session was interrupted by the user before completion but resulted in a fully functional application.

### Files Created

| File | Description |
|------|-------------|
| `app.py` | Main Flask application (~363 lines) |
| `requirements.txt` | Python dependencies (`flask>=2.3`) |
| `templates/base.html` | Base HTML template with CSS variables |
| `templates/index.html` | Message list with attempts and avg score columns |
| `templates/create_message.html` | Form to enter original NTS radiogram |
| `templates/receive_message.html` | Form for operator to enter received message |
| `templates/score.html` | Score results page with field-by-field breakdown |
| `templates/view_message.html` | View a single original message and its receive attempts |
| `static/style.css` | Stylesheet |
| `nts_messages.db` | SQLite database (auto-created at runtime) |

### Application Architecture

**Database (`nts_messages.db`)** — Two tables:
- `messages` — stores original radiograms as transmitted
- `received_messages` — stores operator-entered copies linked to originals

**Scoring Engine (`app.py:96–194`)** — Weighted field scoring across 16 NTS radiogram fields:

| Field | Weight | Mode |
|-------|--------|------|
| Message Number | 5% | exact |
| Precedence | 10% | exact |
| Handling Instructions | 3% | exact |
| Station of Origin | 5% | fuzzy |
| Check (Word Count) | 8% | exact |
| Place of Origin | 5% | fuzzy |
| Time Filed | 2% | exact |
| Date Filed | 5% | fuzzy |
| To: Name | 10% | fuzzy |
| To: Address | 4% | fuzzy |
| To: City | 4% | fuzzy |
| To: State | 3% | exact |
| To: ZIP | 3% | exact |
| To: Phone | 5% | digits |
| Message Text | 18% | words |
| Signature | 10% | fuzzy |

**Scoring modes:**
- `exact` — full match = 1.0, partial containment = 0.5, otherwise 0.0
- `fuzzy` — `difflib.SequenceMatcher` ratio
- `words` — word-level matching ratio (NTS word count)
- `digits` — digits-only comparison via `SequenceMatcher`

**Routes:**
- `GET /` — message list with attempt counts and average scores
- `GET/POST /message/new` — create original radiogram
- `GET /message/<id>` — view message and receive attempts
- `GET/POST /message/<id>/receive` — enter received copy and get score
- `POST /message/<id>/delete` — delete message and all receive attempts

---

## Session 2 — Interaction Log
**Session ID:** `5b074be9-d6c5-4b80-af85-87e18fb45205`
**Timestamp:** 2026-04-12 00:28 UTC

### User Prompt

> place all interactions with this folder and claude into a markdown file. Including the prompt that was issued in claude code for this folder earlier today.

### Claude Response Summary

Claude read the session JSONL files from `~/.claude/projects/-home-mpayne-git-N0LJD/`, extracted the conversation history, reviewed the application files, and produced this document (`CLAUDE_INTERACTIONS.md`).

---

## Running the Application

```bash
cd /home/mpayne/git/N0LJD
python3 -m venv venv          # if not already done
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000` in a browser.
