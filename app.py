"""
NTS Message Scoring Application
Allows net operators to enter received NTS radiogram messages
and score them for accuracy against the original.
"""

import sqlite3
import difflib
import re
from flask import Flask, render_template, request, redirect, url_for, flash, g

app = Flask(__name__)
app.secret_key = 'nts-scoring-app-secret'
DATABASE = 'nts_messages.db'

PRECEDENCES = ['ROUTINE', 'WELFARE', 'PRIORITY', 'EMERGENCY']
HANDLING_INSTRUCTIONS = [
    '', 'HXA', 'HXB', 'HXC', 'HXD', 'HXE', 'HXF', 'HXG'
]

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS messages (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_number          TEXT    NOT NULL,
            precedence          TEXT    NOT NULL,
            handling            TEXT    DEFAULT '',
            station_of_origin   TEXT    NOT NULL,
            check_count         TEXT    NOT NULL,
            place_of_origin     TEXT    NOT NULL,
            time_filed          TEXT    DEFAULT '',
            date_filed          TEXT    NOT NULL,
            to_name             TEXT    NOT NULL,
            to_address          TEXT    DEFAULT '',
            to_city             TEXT    DEFAULT '',
            to_state            TEXT    DEFAULT '',
            to_zip              TEXT    DEFAULT '',
            to_phone            TEXT    DEFAULT '',
            message_text        TEXT    NOT NULL,
            signature           TEXT    NOT NULL,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS received_messages (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id         INTEGER NOT NULL,
            operator_callsign   TEXT    NOT NULL,
            msg_number          TEXT    DEFAULT '',
            precedence          TEXT    DEFAULT '',
            handling            TEXT    DEFAULT '',
            station_of_origin   TEXT    DEFAULT '',
            check_count         TEXT    DEFAULT '',
            place_of_origin     TEXT    DEFAULT '',
            time_filed          TEXT    DEFAULT '',
            date_filed          TEXT    DEFAULT '',
            to_name             TEXT    DEFAULT '',
            to_address          TEXT    DEFAULT '',
            to_city             TEXT    DEFAULT '',
            to_state            TEXT    DEFAULT '',
            to_zip              TEXT    DEFAULT '',
            to_phone            TEXT    DEFAULT '',
            message_text        TEXT    DEFAULT '',
            signature           TEXT    DEFAULT '',
            total_score         REAL,
            submitted_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (original_id) REFERENCES messages(id)
        );
    ''')
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

FIELD_CONFIG = [
    # (field_key,           label,                  weight, scoring_mode)
    ('msg_number',          'Message Number',        0.05,  'exact'),
    ('precedence',          'Precedence',            0.10,  'exact'),
    ('handling',            'Handling Instructions', 0.03,  'exact'),
    ('station_of_origin',   'Station of Origin',     0.05,  'fuzzy'),
    ('check_count',         'Check (Word Count)',     0.08,  'exact'),
    ('place_of_origin',     'Place of Origin',       0.05,  'fuzzy'),
    ('time_filed',          'Time Filed',            0.02,  'exact'),
    ('date_filed',          'Date Filed',            0.05,  'fuzzy'),
    ('to_name',             'To: Name',              0.10,  'fuzzy'),
    ('to_address',          'To: Address',           0.04,  'fuzzy'),
    ('to_city',             'To: City',              0.04,  'fuzzy'),
    ('to_state',            'To: State',             0.03,  'exact'),
    ('to_zip',              'To: ZIP',               0.03,  'exact'),
    ('to_phone',            'To: Phone',             0.05,  'digits'),
    ('message_text',        'Message Text',          0.18,  'words'),
    ('signature',           'Signature',             0.10,  'fuzzy'),
]


def normalize(s):
    """Lowercase, collapse whitespace, strip punctuation noise."""
    s = (s or '').strip().lower()
    s = re.sub(r'\s+', ' ', s)
    return s


def digits_only(s):
    return re.sub(r'\D', '', s or '')


def count_nts_words(text):
    """NTS word count: each space-separated token is one word."""
    return len(text.split()) if text.strip() else 0


def score_field(original, entered, mode):
    orig = normalize(original)
    ent = normalize(entered)

    if mode == 'exact':
        return 1.0 if orig == ent else (0.5 if orig and ent and orig in ent else 0.0)

    if mode == 'digits':
        od = digits_only(orig)
        ed = digits_only(ent)
        if not od and not ed:
            return 1.0
        if not od or not ed:
            return 0.0
        return 1.0 if od == ed else difflib.SequenceMatcher(None, od, ed).ratio()

    if mode == 'words':
        orig_words = orig.split()
        ent_words = ent.split()
        if not orig_words and not ent_words:
            return 1.0
        if not orig_words or not ent_words:
            return 0.0
        # Score by word-level matching
        matcher = difflib.SequenceMatcher(None, orig_words, ent_words)
        matching = sum(t.size for t in matcher.get_matching_blocks())
        return matching / max(len(orig_words), len(ent_words))

    # fuzzy
    if not orig and not ent:
        return 1.0
    if not orig or not ent:
        return 0.0
    return difflib.SequenceMatcher(None, orig, ent).ratio()


def score_message(original, received):
    results = []
    weighted_sum = 0.0
    total_weight = sum(w for _, _, w, _ in FIELD_CONFIG)

    for field, label, weight, mode in FIELD_CONFIG:
        orig_val = str(original[field] or '')
        recv_val = str(received.get(field) or '')
        s = score_field(orig_val, recv_val, mode)
        weighted_sum += s * weight
        results.append({
            'field':     field,
            'label':     label,
            'weight':    weight,
            'weight_pct': round(weight / total_weight * 100, 1),
            'original':  orig_val,
            'entered':   recv_val,
            'score':     s,
            'score_pct': round(s * 100, 1),
            'perfect':   s >= 0.99,
            'good':      0.75 <= s < 0.99,
            'poor':      s < 0.75,
        })

    total = (weighted_sum / total_weight) * 100
    return results, round(total, 1)


def auto_check(text):
    """Return the NTS word count for a message text."""
    return str(count_nts_words(text))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    db = get_db()
    messages = db.execute(
        'SELECT m.*, COUNT(r.id) as attempts, AVG(r.total_score) as avg_score '
        'FROM messages m '
        'LEFT JOIN received_messages r ON r.original_id = m.id '
        'GROUP BY m.id ORDER BY m.created_at DESC'
    ).fetchall()
    return render_template('index.html', messages=messages)


@app.route('/message/new', methods=['GET', 'POST'])
def create_message():
    if request.method == 'POST':
        f = request.form
        msg_text = (f.get('message_text') or '').strip()
        check = f.get('check_count', '').strip() or auto_check(msg_text)
        db = get_db()
        db.execute(
            '''INSERT INTO messages
               (msg_number, precedence, handling, station_of_origin, check_count,
                place_of_origin, time_filed, date_filed,
                to_name, to_address, to_city, to_state, to_zip, to_phone,
                message_text, signature)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (
                f.get('msg_number', '').strip(),
                (f.get('precedence') or 'ROUTINE').upper(),
                (f.get('handling') or '').strip().upper(),
                f.get('station_of_origin', '').strip().upper(),
                check,
                f.get('place_of_origin', '').strip().upper(),
                f.get('time_filed', '').strip(),
                f.get('date_filed', '').strip(),
                f.get('to_name', '').strip(),
                f.get('to_address', '').strip(),
                f.get('to_city', '').strip(),
                f.get('to_state', '').strip().upper(),
                f.get('to_zip', '').strip(),
                f.get('to_phone', '').strip(),
                msg_text,
                f.get('signature', '').strip(),
            )
        )
        db.commit()
        flash('Message saved to database.', 'success')
        return redirect(url_for('index'))

    return render_template('create_message.html',
                           precedences=PRECEDENCES,
                           handling_instructions=HANDLING_INSTRUCTIONS)


@app.route('/message/<int:msg_id>')
def view_message(msg_id):
    db = get_db()
    message = db.execute('SELECT * FROM messages WHERE id = ?', (msg_id,)).fetchone()
    if not message:
        flash('Message not found.', 'error')
        return redirect(url_for('index'))
    received = db.execute(
        'SELECT * FROM received_messages WHERE original_id = ? ORDER BY submitted_at DESC',
        (msg_id,)
    ).fetchall()
    return render_template('view_message.html', message=message, received=received)


@app.route('/message/<int:msg_id>/receive', methods=['GET', 'POST'])
def receive_message(msg_id):
    db = get_db()
    original = db.execute('SELECT * FROM messages WHERE id = ?', (msg_id,)).fetchone()
    if not original:
        flash('Message not found.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        f = request.form
        received = {k: (f.get(k) or '') for k in f}

        field_results, total_score = score_message(original, received)

        db.execute(
            '''INSERT INTO received_messages
               (original_id, operator_callsign, msg_number, precedence, handling,
                station_of_origin, check_count, place_of_origin, time_filed, date_filed,
                to_name, to_address, to_city, to_state, to_zip, to_phone,
                message_text, signature, total_score)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (
                msg_id,
                f.get('operator_callsign', '').strip().upper(),
                f.get('msg_number', '').strip(),
                (f.get('precedence') or '').strip().upper(),
                (f.get('handling') or '').strip().upper(),
                f.get('station_of_origin', '').strip().upper(),
                f.get('check_count', '').strip(),
                f.get('place_of_origin', '').strip().upper(),
                f.get('time_filed', '').strip(),
                f.get('date_filed', '').strip(),
                f.get('to_name', '').strip(),
                f.get('to_address', '').strip(),
                f.get('to_city', '').strip(),
                f.get('to_state', '').strip().upper(),
                f.get('to_zip', '').strip(),
                f.get('to_phone', '').strip(),
                f.get('message_text', '').strip(),
                f.get('signature', '').strip(),
                total_score,
            )
        )
        db.commit()

        return render_template('score.html',
                               original=original,
                               received=f,
                               field_results=field_results,
                               total_score=total_score,
                               operator=f.get('operator_callsign', '').upper())

    return render_template('receive_message.html',
                           message=original,
                           precedences=PRECEDENCES)


@app.route('/message/<int:msg_id>/delete', methods=['POST'])
def delete_message(msg_id):
    db = get_db()
    db.execute('DELETE FROM received_messages WHERE original_id = ?', (msg_id,))
    db.execute('DELETE FROM messages WHERE id = ?', (msg_id,))
    db.commit()
    flash('Message deleted.', 'info')
    return redirect(url_for('index'))


# ---------------------------------------------------------------------------
# Template filter
# ---------------------------------------------------------------------------

@app.template_filter('score_class')
def score_class(score):
    if score >= 90:
        return 'score-excellent'
    if score >= 75:
        return 'score-good'
    if score >= 50:
        return 'score-fair'
    return 'score-poor'


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
