# -*- coding: utf-8 -*-
"""SQLite 存取层。"""
import json
import sqlite3
from datetime import datetime

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS charts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  round INTEGER NOT NULL,
  input_json TEXT NOT NULL,
  variant_json TEXT NOT NULL,
  chart_json TEXT NOT NULL,
  fortune_json TEXT NOT NULL,
  statements_json TEXT NOT NULL,
  answers_json TEXT,
  reject_rate REAL,
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | confirmed
  is_final INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  chart_id INTEGER,
  title TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
CREATE INDEX IF NOT EXISTS idx_charts_user ON charts(user_id);
CREATE INDEX IF NOT EXISTS idx_msgs_conv ON messages(conversation_id);
"""


def conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def init():
    with conn() as c:
        c.executescript(SCHEMA)


def now():
    return datetime.now().isoformat(timespec="seconds")


# ---------- users ----------
def create_user(username, pw_hash):
    with conn() as c:
        cur = c.execute("INSERT INTO users(username, password_hash, created_at) VALUES(?,?,?)",
                        (username, pw_hash, now()))
        return cur.lastrowid


def get_user(username):
    with conn() as c:
        return c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


def get_user_by_id(uid):
    with conn() as c:
        return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


# ---------- charts ----------
def save_chart(user_id, round_no, birth_input, variant, chart, fortune, statements):
    with conn() as c:
        cur = c.execute(
            """INSERT INTO charts(user_id, round, input_json, variant_json, chart_json,
               fortune_json, statements_json, created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (user_id, round_no, json.dumps(birth_input, ensure_ascii=False),
             json.dumps(variant, ensure_ascii=False), json.dumps(chart, ensure_ascii=False),
             json.dumps(fortune, ensure_ascii=False), json.dumps(statements, ensure_ascii=False),
             now()))
        return cur.lastrowid


def update_chart_feedback(chart_id, answers, reject_rate, status, is_final=False):
    with conn() as c:
        c.execute("""UPDATE charts SET answers_json=?, reject_rate=?, status=?, is_final=?
                     WHERE id=?""",
                  (json.dumps(answers, ensure_ascii=False), reject_rate, status,
                   1 if is_final else 0, chart_id))
        if is_final:
            c.execute("UPDATE charts SET is_final=0 WHERE user_id=(SELECT user_id FROM charts WHERE id=?) AND id!=? AND status='confirmed'",
                      (chart_id, chart_id))


def get_chart(chart_id):
    with conn() as c:
        return c.execute("SELECT * FROM charts WHERE id=?", (chart_id,)).fetchone()


def get_round_chart(user_id, round_no):
    with conn() as c:
        return c.execute("SELECT * FROM charts WHERE user_id=? AND round=? AND status='pending' ORDER BY id DESC LIMIT 1",
                         (user_id, round_no)).fetchone()


def get_final_chart(user_id):
    with conn() as c:
        return c.execute("SELECT * FROM charts WHERE user_id=? AND is_final=1 ORDER BY id DESC LIMIT 1",
                         (user_id,)).fetchone()


def list_user_charts(user_id):
    with conn() as c:
        return c.execute("SELECT id, round, status, is_final, reject_rate, created_at, variant_json "
                         "FROM charts WHERE user_id=? ORDER BY id", (user_id,)).fetchall()


# ---------- conversations / messages ----------
def create_conversation(user_id, chart_id, title):
    with conn() as c:
        cur = c.execute("INSERT INTO conversations(user_id, chart_id, title, created_at) VALUES(?,?,?,?)",
                        (user_id, chart_id, title, now()))
        return cur.lastrowid


def get_conversation(conv_id, user_id):
    with conn() as c:
        return c.execute("SELECT * FROM conversations WHERE id=? AND user_id=?", (conv_id, user_id)).fetchone()


def list_conversations(user_id):
    with conn() as c:
        return c.execute("SELECT * FROM conversations WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()


def add_message(conv_id, role, content):
    with conn() as c:
        c.execute("INSERT INTO messages(conversation_id, role, content, created_at) VALUES(?,?,?,?)",
                  (conv_id, role, content, now()))


def count_user_messages(conv_id):
    with conn() as c:
        return c.execute("SELECT COUNT(*) n FROM messages WHERE conversation_id=? AND role='user'",
                         (conv_id,)).fetchone()["n"]


def get_messages(conv_id):
    with conn() as c:
        return c.execute("SELECT role, content, created_at FROM messages WHERE conversation_id=? ORDER BY id",
                         (conv_id,)).fetchall()
