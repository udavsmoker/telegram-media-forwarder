# Movie Download Bot

A Telegram bot that searches for videos by code and forwards them to users. Features automatic indexing, manual indexing, and admin management interface.

## Features

- Auto-indexing of new channel posts
- Manual indexing via forwarded messages or links
- SQLite database for fast lookups
- Admin interface for database management
- Pattern-based code search
- Privacy-focused (source channel hidden from users)

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a bot via [@BotFather](https://t.me/BotFather) and get your bot token

3. Add the bot as admin to your channel

4. Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot)

5. Configure environment:
   - Copy `.env.example` to `.env`
   - Fill in your credentials:
     ```
     BOT_TOKEN=your_bot_token
     ADMIN_USER_ID=your_telegram_user_id
     CHANNEL_ID=-1001234567890
     ```

6. Run the bot:
   ```bash
   python bot.py
   ```

## Usage

### Regular Users
- Send a movie code (e.g., `MOV123`) to search and receive the video

### Admin
- Access admin panel via `/start`
- Forward channel messages to index them
- Send channel message links to index them
- Use admin panel buttons:
  - Stats - View database statistics
  - List All - View recent indexed codes
  - Search - Find codes by pattern
  - Delete - Remove codes from database

## Requirements

- Python 3.8+
- python-telegram-bot
- python-dotenv
