import os
import re
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode, ChatType
from dotenv import load_dotenv

sqlite3.register_adapter(datetime, lambda val: val.isoformat())
sqlite3.register_converter("timestamp", lambda val: datetime.fromisoformat(val.decode()))

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))
DB_FILE = 'media.db'
CODE_PATTERN = re.compile(r'\b([A-Z]+\d+)\b')


class MovieDatabase:
    def __init__(self, db_file):
        self.db_file = db_file
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS movies (
                code TEXT PRIMARY KEY,
                message_id INTEGER NOT NULL,
                caption TEXT,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def add_movie(self, code, message_id, caption=None):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO movies (code, message_id, caption, indexed_at)
            VALUES (?, ?, ?, ?)
        ''', (code, message_id, caption, datetime.now()))
        conn.commit()
        conn.close()
    
    def add_movies_from_message(self, message_id, caption):
        codes = CODE_PATTERN.findall(caption)
        for code in codes:
            self.add_movie(code, message_id, caption)
        return len(codes)
    
    def get_movie(self, code):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT message_id, caption FROM movies WHERE code = ?', (code,))
        result = cursor.fetchone()
        conn.close()
        return result
    
    def delete_movie(self, code):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM movies WHERE code = ?', (code,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted > 0
    
    def get_all_codes(self, limit=50, offset=0):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT code, message_id, indexed_at 
            FROM movies 
            ORDER BY indexed_at DESC 
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_total_movies(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM movies')
        result = cursor.fetchone()[0]
        conn.close()
        return result
    
    def search_codes(self, pattern):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT code, message_id, caption 
            FROM movies 
            WHERE code LIKE ? 
            ORDER BY code
            LIMIT 20
        ''', (f'%{pattern}%',))
        results = cursor.fetchall()
        conn.close()
        return results


db = MovieDatabase(DB_FILE)


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_USER_ID


async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post and update.channel_post.chat.id == CHANNEL_ID:
        message = update.channel_post
        if message.video or message.document:
            caption = message.caption or ""
            if caption:
                count = db.add_movies_from_message(message.message_id, caption)
                if count > 0:
                    print(f"Auto-indexed {count} code(s) from message {message.message_id}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if is_admin(user_id):
        keyboard = [
            [InlineKeyboardButton("Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("List All", callback_data="admin_list")],
            [InlineKeyboardButton("Search", callback_data="admin_search")],
            [InlineKeyboardButton("Delete", callback_data="admin_delete")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "*Movie Bot - Admin Panel*\n\n"
            "You can:\n"
            "• Send a movie code to search (e.g., MOV123)\n"
            "• Forward a message from the channel to index it\n"
            "• Send a channel message link to index it\n"
            "• Use the buttons below to manage the database",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Welcome! Send me a movie code (e.g., MOV123) to search."
        )


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    data = query.data
    
    if data == "admin_stats":
        total = db.get_total_movies()
        await query.edit_message_text(
            f"*Database Statistics*\n\n"
            f"Total indexed videos: {total}\n\n"
            f"Use /start to return to menu",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "admin_list":
        codes = db.get_all_codes(limit=20)
        if codes:
            text = "*Recent Codes:*\n\n"
            for code, msg_id, indexed_at in codes:
                text += f"`{code}` (msg: {msg_id})\n"
            text += f"\n_Showing last 20 entries_\nUse /start to return"
        else:
            text = "No codes in database yet.\n\nUse /start to return"
        
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "admin_search":
        await query.edit_message_text(
            "Send me a search pattern.\n\n"
            "Example: `MOV` to find all codes starting with MOV\n\n"
            "Use /start to cancel",
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data['awaiting'] = 'search'
    
    elif data == "admin_delete":
        await query.edit_message_text(
            "Send me the code to delete.\n\n"
            "Example: `MOV123`\n\n"
            "Use /start to cancel",
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data['awaiting'] = 'delete'


async def forwarded_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    message = update.message
    
    if message.forward_origin and hasattr(message.forward_origin, 'chat'):
        if message.forward_origin.chat.id == CHANNEL_ID:
            caption = message.caption or message.text or ""
            
            if caption:
                message_id = message.forward_origin.message_id
                count = db.add_movies_from_message(message_id, caption)
                
                if count > 0:
                    await message.reply_text(f"Indexed {count} code(s) from this message!")
                else:
                    await message.reply_text("No codes found in this message.")
            else:
                await message.reply_text("This message has no caption to index.")


async def message_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    text = update.message.text
    
    if context.user_data.get('awaiting') == 'search':
        results = db.search_codes(text.upper())
        if results:
            response = "*Search Results:*\n\n"
            for code, msg_id, caption in results:
                response += f"`{code}` - [Link](https://t.me/c/{str(CHANNEL_ID)[4:]}/{msg_id})\n"
            response += f"\n_Found {len(results)} results_"
        else:
            response = "No matches found."
        
        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
        context.user_data.pop('awaiting', None)
        return
    
    elif context.user_data.get('awaiting') == 'delete':
        code = text.upper().strip()
        if db.delete_movie(code):
            await update.message.reply_text(f"Deleted `{code}` from database", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"Code `{code}` not found in database", parse_mode=ParseMode.MARKDOWN)
        
        context.user_data.pop('awaiting', None)
        return
    
    link_pattern = r't\.me/c/(\d+)/(\d+)'
    match = re.search(link_pattern, text)
    
    if match:
        private_id = int(match.group(1))
        chat_id = -1000000000000 - private_id
        message_id = int(match.group(2))
        
        if chat_id == CHANNEL_ID:
            try:
                msg = await context.bot.forward_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=CHANNEL_ID,
                    message_id=message_id
                )
                
                caption = msg.caption or msg.text or ""
                
                if caption:
                    count = db.add_movies_from_message(message_id, caption)
                    await update.message.reply_text(f"Indexed {count} code(s) from the linked message!")
                else:
                    await update.message.reply_text("The linked message has no caption.")
                
                await msg.delete()
                
            except Exception as e:
                await update.message.reply_text(f"Error: {str(e)}")
                print(f"Error processing link: {e}")
        else:
            await update.message.reply_text("This link is not from the configured channel.")


async def code_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip().upper()
    
    if not re.match(r'^[A-Z]+\d+$', code):
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("Please send a valid movie code (e.g., MOV123)")
        return
    
    status_msg = await update.message.reply_text(
        f"Searching for `{code}`...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        result = db.get_movie(code)
        
        if result:
            message_id, caption = result
            
            await context.bot.copy_message(
                chat_id=update.effective_chat.id,
                from_chat_id=CHANNEL_ID,
                message_id=message_id,
                caption=f"Found: `{code}`" + (f"\n\n{caption}" if caption else ""),
                parse_mode=ParseMode.MARKDOWN
            )
            
            await status_msg.delete()
        else:
            await status_msg.edit_text(
                f"Sorry, no video found with code `{code}`",
                parse_mode=ParseMode.MARKDOWN
            )
    
    except Exception as e:
        await status_msg.edit_text(f"Error: {str(e)}")
        print(f"Error searching for {code}: {e}")


def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Chat(CHANNEL_ID),
        channel_post_handler
    ))
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern=r'^admin_'))
    
    application.add_handler(MessageHandler(
        filters.FORWARDED & filters.ChatType.PRIVATE,
        forwarded_message_handler
    ))
    
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & filters.Regex(r't\.me/c/\d+/\d+'),
        message_link_handler
    ))
    
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        lambda update, context: (
            message_link_handler(update, context)
            if context.user_data.get('awaiting') or 't.me/' in update.message.text
            else code_search_handler(update, context)
        )
    ))
    
    print("Bot is starting...")
    print("Bot is running! Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
