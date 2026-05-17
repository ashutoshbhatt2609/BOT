# 🤖 Rotaract Club Telegram Bot

A professional, role-based task management and communication system for Rotaract Club built with Python and `python-telegram-bot`.

---

## 📋 Features

| Feature | Description |
|---|---|
| **Role-Based Access** | Core, Director, Member permissions |
| **Task Management** | Create, assign, track tasks with deadlines & priorities |
| **Automated Reminders** | Daily, Urgent (5h), 24h/5h/1h deadline alerts |
| **Escalation System** | Auto-escalate overdue tasks up the hierarchy |
| **Inter-Avenue Requests** | Avenues can request work from each other |
| **Weekly Reports** | Auto-generated performance report every Monday |
| **File/Message Logging** | All group messages and files are logged |
| **SQLite Database** | Lightweight, upgradeable to PostgreSQL/MongoDB |

---

## 🚀 Quick Start

### 1. Create a Bot
- Message [@BotFather](https://t.me/BotFather) on Telegram
- Run `/newbot` and get your **API token**

### 2. Setup Environment
```bash
# Clone the repo
git clone <your-repo-url>
cd BOT

# Create virtual environment
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Create .env file
copy .env.example .env
# Edit .env and fill in BOT_TOKEN, CORE_GROUP_CHAT_ID
```

### 3. Bootstrap First Admin
After the first run, manually set yourself as Core in the database:
```bash
python bootstrap_admin.py <YOUR_TELEGRAM_ID> "Your Name"
```

### 4. Run the Bot
```bash
python main.py
```

---

## 📁 Project Structure

```
BOT/
├── main.py                    # Entry point
├── config.py                  # Config & constants
├── database.py                # SQLite database layer
├── scheduler.py               # APScheduler jobs
├── utils.py                   # Shared formatting helpers
├── handlers/
│   ├── common_handlers.py     # /start, /help
│   ├── admin_handlers.py      # Core-only commands
│   ├── task_handlers.py       # Task lifecycle
│   └── request_handlers.py    # Inter-avenue requests
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## 🏛️ Organizational Hierarchy

```
Core Leadership (President, VP, Secretary, Treasurer…)
        ↓
Avenue Directors (Technical, Media, Editorial…)
        ↓
Avenue Members
```

---

## 🤖 Bot Commands

| Command | Who | Purpose |
|---|---|---|
| `/start` | All | Register & welcome |
| `/help` | All | Command reference |
| `/newtask` | Core / Director | Create a new task |
| `/mytasks` | All | View avenue tasks |
| `/pending` | All | View pending tasks |
| `/completed` | All | View completed tasks |
| `/avenuetasks` | All | All tasks for your avenue |
| `/request` | All | Send inter-avenue request |
| `/report` | Core | Generate weekly report |
| `/announce` | Core | Broadcast to all |
| `/adduser` | Core | Register a user |
| `/removeuser` | Core | Remove a user |
| `/setrole` | Core | Change user role |
| `/setavenue` | Core | Set user avenue |
| `/listusers` | Core | List all members |

---

## ⏰ Automated Schedule

| Job | Trigger |
|---|---|
| Daily Reminder | Every day at 9:00 AM IST |
| Urgent Task Alert | Every 5 hours |
| 24h Deadline Alert | Checked hourly |
| 5h Deadline Alert | Checked every 30 min |
| 1h Deadline Alert | Checked every 15 min |
| Escalation Check | Every 2 hours |
| Weekly Report | Every Monday at 8:00 AM IST |

---

## 🚀 Deployment

### Render / Railway
- Push to GitHub
- Create a new **Web Service** (or Worker)
- Set environment variables from `.env.example`
- Start command: `python main.py`

### VPS (Ubuntu)
```bash
pip install -r requirements.txt
nohup python main.py &
# Or use systemd/supervisor for production
```

---

## 📊 Database Schema

- `users` — Telegram users with roles & avenues
- `avenues` — 9 club avenues
- `tasks` — Tasks with deadlines, priorities, statuses
- `requests` — Inter-avenue work requests
- `reports` — Auto-generated weekly report snapshots
- `messages` — Group message & file logs

---

## 🔮 Future Roadmap

- [ ] Web dashboard (React)
- [ ] Google Sheets export
- [ ] AI-generated summaries
- [ ] QR-based attendance
- [ ] Event planning workflows
- [ ] Approval pipelines
- [ ] Analytics panel

---

*Built with ❤️ for Rotaract Club Operations*
