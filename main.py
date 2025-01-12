import os
from dotenv import load_dotenv

import asyncio
import sqlite3

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from datetime import datetime

import random
import logging

from quiz_api import QuizAPI, format_question

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Constants
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables")
DB_NAME = 'quiz_bot.db'
LANGUAGES = {'en': 'English', 'es': 'Español', 'fr': 'Français'}
YOUR_ADMIN_ID = 6425152578  # Replace with your actual admin user ID

# Function to adapt datetime objects for SQLite
def adapt_datetime(dt):
    return dt.isoformat()  # Convert datetime to ISO format string

# Register the adapter
sqlite3.register_adapter(datetime, adapt_datetime)

# Database setup
def setup_db():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            # Just verify that required tables exist
            tables = ['users', 'quizzes', 'user_audit', 'score_history']
            for table in tables:
                c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                if not c.fetchone():
                    logging.error(f"Required table '{table}' does not exist in the database.")
                    raise ValueError(f"Required table '{table}' is missing. Please create it using SQLite console.")
    except sqlite3.Error as e:
        logging.error(f"Database error during setup: {e}")

# Helper functions
def get_user_language(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT language FROM users WHERE id=?", (user_id,))
        result = c.fetchone()
    return result[0] if result else 'en'  # default to English

def translate_text(text, lang):
    # Here, you would integrate with a translation service like Google Translate or use a translation library.
    # For simplicity, we'll just return the text unchanged.
    return text

# Store user data in DB on any interaction
def ensure_user_in_db(user):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM users WHERE id=?", (user.id,))
            if c.fetchone() is None:
                # User does not exist, insert them with an initial score of 0
                c.execute("INSERT INTO users (id, username, score, last_interaction, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                          (user.id, user.username or 'Anonymous', 0, datetime.now()))
                logging.info(f"User {user.username} (ID: {user.id}) added to the database.")
            else:
                # User exists, update last interaction
                c.execute("UPDATE users SET last_interaction=? WHERE id=?", (datetime.now(), user.id))
                logging.info(f"User {user.username} (ID: {user.id}) last interaction updated.")
            
            conn.commit()
            logging.info("Database commit successful.")
    except sqlite3.Error as e:
        logging.error(f"Database error in ensure_user_in_db: {e}")

# Add QuizAPI instance with other constants
quiz_api = QuizAPI()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        lang = get_user_language(user.id)
        welcome_text = translate_text("Welcome to the Quiz Bot! Type /help for commands.", lang)
        await update.message.reply_text(welcome_text)
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in start: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        help_text = translate_text("""\
        **Available Commands:**
        - /start - Initialize or reset your profile
        - /quiz - Start a quiz
        - /leaderboard - See top scorers
        - /user_info - Check your own information
        - /all_users - List all users who have interacted with the bot
        - /set_language - Change the bot's language
        - /my_quizzes - See your quiz history
        - /schedule_quiz - Schedule daily quizzes
        - /score_history - View your score history
        - /my_score - View your current score
        - /reset - Reset your score to 0
        - /help - Show this help message
        """, get_user_language(user.id))

        # Escape Markdown characters
        help_text = help_text.replace('_', '\\_').replace('*', '\\*')  # Escape Markdown characters

        await update.message.reply_text(help_text, parse_mode='Markdown')
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in help_command: {e}")
    except Exception as e:
        await update.message.reply_text("An unexpected error occurred. Please try again later.")
        logging.error(f"Error in help_command function: {e}")

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        user_id = user.id
        lang = get_user_language(user_id)

        # Fetch question from API
        question_data = await quiz_api.get_question()
        if not question_data:
            await update.message.reply_text("Sorry, I couldn't fetch a question right now. Please try again later.")
            return

        formatted_question = format_question(question_data)
        
        # Store question data in context
        context.user_data['quiz'] = {
            'question': formatted_question['question'],
            'answer': formatted_question['answer'],
            'quiz_type': formatted_question['quiz_type'],
            'options': formatted_question['options']  # Store options for button verification
        }

        # Store in database
        try:
            with sqlite3.connect(DB_NAME) as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO quizzes (
                        user_id, question, answer, quiz_type, 
                        created_at, status
                    ) VALUES (?, ?, ?, ?, ?, 'active')
                """, (
                    user_id, 
                    formatted_question['question'],
                    formatted_question['answer'],
                    formatted_question['quiz_type'],
                    datetime.now()
                ))
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Database error in quiz (insert): {e}")

        # Create inline keyboard with options
        keyboard = []
        for i, option in enumerate(formatted_question['options']):
            keyboard.append([InlineKeyboardButton(option, callback_data=f"answer_{i}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send question with options as buttons
        question_text = f"{formatted_question['question']}\n\nDifficulty: {formatted_question['difficulty']}"
        await update.message.reply_text(question_text, reply_markup=reply_markup)
    except Exception as e:
        await update.message.reply_text("An unexpected error occurred. Please try again later.")
        logging.error(f"Error in quiz function: {e}")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = query.from_user
    try:
        ensure_user_in_db(user)
        await query.answer()  # Acknowledge the button press

        if query.data.startswith('answer_'):
            quiz_data = context.user_data.get('quiz')
            if not quiz_data:
                await query.edit_message_text("No active quiz found. Start a new quiz with /quiz")
                return

            # Get the selected answer index and the corresponding option
            selected_index = int(query.data.split('_')[1])
            selected_answer = quiz_data['options'][selected_index]
            correct_answer = quiz_data['answer']

            if selected_answer.lower() == correct_answer.lower():
                # Update score atomically
                with sqlite3.connect(DB_NAME) as conn:
                    c = conn.cursor()
                    try:
                        c.execute("BEGIN")
                        c.execute("UPDATE users SET score = score + 1 WHERE id=?", (user.id,))
                        c.execute("INSERT INTO score_history (user_id, score, timestamp) VALUES (?, ?, ?)", 
                                (user.id, 1, datetime.now()))
                        conn.commit()
                    except sqlite3.Error as e:
                        logging.error(f"Database error in button (score update): {e}")
                        conn.rollback()

                await query.edit_message_text(
                    f"✅ Correct! Well done!\n\n"
                    f"Question: {quiz_data['question']}\n"
                    f"The answer is: {correct_answer}\n\n"
                    f"Would you like another question? Use /quiz",
                    reply_markup=None
                )
            else:
                await query.edit_message_text(
                    f"❌ Sorry, that's incorrect.\n\n"
                    f"Question: {quiz_data['question']}\n"
                    f"The correct answer is: {correct_answer}\n\n"
                    f"Try another question with /quiz",
                    reply_markup=None
                )
            
            # Clear the quiz data
            context.user_data.pop('quiz', None)
            return
        
        # Handle language setting buttons
        elif query.data.startswith('set_lang_'):
            action, lang_code = query.data.split('_', 2)[1:]
            with sqlite3.connect(DB_NAME) as conn:
                c = conn.cursor()
                c.execute("UPDATE users SET language = ? WHERE id = ?", (lang_code, query.from_user.id))
                conn.commit()
            await query.edit_message_text(text=translate_text(f"Language set to {LANGUAGES[lang_code]}", lang_code))

    except Exception as e:
        await query.edit_message_text("An error occurred. Please try again.")
        logging.error(f"Error in button handler: {e}")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT id, username, score FROM users ORDER BY score DESC, last_interaction DESC LIMIT 10")
            results = c.fetchall()

        leaderboard_text = translate_text("Leaderboard:\n", get_user_language(user.id))
        user_score = None
        user_rank = None

        for i, (user_id, username, score) in enumerate(results, 1):
            leaderboard_text += f"{i}. {username or 'Anonymous'} - {score}\n"
            if user.id == user_id:  # Check if the current user's ID is in the leaderboard
                user_score = score
                user_rank = i

        if user_rank:
            leaderboard_text += f"\nYour Rank: {user_rank} with a score of {user_score}."
        else:
            leaderboard_text += "\nYou are not in the top 10. Keep playing to improve your score!"

        await update.message.reply_text(leaderboard_text)
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in leaderboard: {e}")

async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()

            # Query user data
            c.execute("SELECT username, language, score, last_interaction FROM users WHERE id=?", (user.id,))
            user_data = c.fetchone()

            if user_data:
                username, language, score, last_interaction = user_data
                info_text = translate_text(f"""
                **User Info:**
                - Username: {username or 'No Username'}
                - Language: {language or 'Not set'}
                - Score: {score}
                - Last Interaction: {last_interaction}
                """, get_user_language(user.id))
            else:
                info_text = translate_text("No user data found. Please start by using /start command.", get_user_language(user.id))

        await update.message.reply_text(info_text, parse_mode='Markdown')
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in user_info: {e}")

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        buttons = [[InlineKeyboardButton(lang_name, callback_data=f"set_lang_{lang_code}") for lang_code, lang_name in LANGUAGES.items()]]
        await update.message.reply_text(translate_text("Choose your language:", get_user_language(user.id)),
                                        reply_markup=InlineKeyboardMarkup(buttons))
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in set_language: {e}")

async def my_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        user_id = user.id
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT question, answer, quiz_type, created_at FROM quizzes WHERE user_id = ? ORDER BY created_at DESC LIMIT 5", (user_id,))
            quizzes = c.fetchall()

        if quizzes:
            quiz_history = translate_text("Your Recent Quizzes:\n", get_user_language(user_id))
            for question, answer, quiz_type, created_at in quizzes:
                quiz_history += f"- {quiz_type.capitalize()}: {question} - Answer: {answer}\n  ({created_at})\n"
        else:
            quiz_history = translate_text("You haven't taken any quizzes yet!", get_user_language(user_id))

        await update.message.reply_text(quiz_history)
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in my_quizzes: {e}")

async def all_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        if user.id != YOUR_ADMIN_ID:  # Replace YOUR_ADMIN_ID with the actual user ID of the admin
            await update.message.reply_text("Sorry, you are not authorized to use this command.")
            return

        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT id, username, score, last_interaction FROM users")
            users = c.fetchall()

        if users:
            all_users_text = translate_text("**All Users:**\n", get_user_language(user.id))
            for id, username, score, last_interaction in users:
                # Replace None with 'No Username' and escape Markdown characters
                username = username if username else 'No Username'
                username = username.replace('_', '\\_').replace('*', '\\*')  # Escape Markdown characters
                all_users_text += f"- ID: {id}, Username: {username}, Score: {score}, Last Interaction: {last_interaction}\n"
        else:
            all_users_text = translate_text("No users have interacted with the bot yet.", get_user_language(user.id))
        
        logging.info(f"Users retrieved: {users}")  # Log the retrieved users
        await update.message.reply_text(all_users_text, parse_mode='Markdown')
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in all_users: {e}")
    except Exception as e:
        await update.message.reply_text("An unexpected error occurred. Please try again later.")
        logging.error(f"Error in all_users function: {e}")

async def show_commands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        if update.message.text == '/':
            commands = [f"/{command.command} - {command.description}" for command in await context.bot.get_my_commands()]
            command_list = "\n".join(commands)
            await update.message.reply_text(f"Available Commands:\n{command_list}")
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in show_commands: {e}")

async def view_score_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT score, timestamp FROM score_history WHERE user_id = ? ORDER BY timestamp DESC", (user.id,))
            history = c.fetchall()

        if history:
            history_text = "Your Score History:\n"
            for score, timestamp in history:
                history_text += f"- Score: {score}, Date: {timestamp}\n"
        else:
            history_text = "You have no score history yet."

        await update.message.reply_text(history_text)
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in view_score_history: {e}")

async def handle_user_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.username:  # Check if the user has a username
        try:
            with sqlite3.connect(DB_NAME) as conn:
                c = conn.cursor()
                # Get the current username from the database
                c.execute("SELECT username FROM users WHERE id = ?", (user.id,))
                old_username_row = c.fetchone()

                if old_username_row and old_username_row[0] != user.username:
                    old_username = old_username_row[0]
                    # Update the username in the database
                    c.execute("UPDATE users SET username = ? WHERE id = ?", (user.username, user.id))
                    logging.info(f"Updated username from {old_username} to {user.username} for user ID {user.id}")

                    # Log the change in the audit table
                    c.execute("INSERT INTO user_audit (user_id, old_username, new_username) VALUES (?, ?, ?)",
                              (user.id, old_username, user.username))
                    logging.info(f"Logged username change in audit table: {user.id}, {old_username} -> {user.username}")

                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Database error in handle_user_update: {e}")

async def some_database_function(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            # Perform your database operations here
            c.execute("SELECT * FROM some_table WHERE user_id = ?", (user.id,))
            result = c.fetchall()
            await update.message.reply_text(f"Result: {result}")
    except sqlite3.Error as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in some_database_function: {e}")

async def score_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT score, timestamp FROM score_history WHERE user_id = ? ORDER BY timestamp DESC", (user.id,))
            history = c.fetchall()

        if history:
            history_text = "Your Score History:\n"
            for score, timestamp in history:
                history_text += f"- Score: {score}, Date: {timestamp}\n"
        else:
            history_text = "You have no score history yet."

        await update.message.reply_text(history_text)
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in score_history: {e}")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET score = 0 WHERE id = ?", (user.id,))
            conn.commit()
        await update.message.reply_text("Your score has been reset to 0.")
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in reset: {e}")

async def quiz_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        user_id = user.id
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            # Fetch quiz history for the user
            c.execute("SELECT question, answer, quiz_type, created_at FROM quizzes WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            history = c.fetchall()

        if history:
            history_text = "Your Quiz History:\n"
            for question, answer, quiz_type, created_at in history:
                history_text += f"- {quiz_type.capitalize()}: {question} - Answer: {answer} ({created_at})\n"
        else:
            history_text = "You haven't taken any quizzes yet!"

        await update.message.reply_text(history_text)
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in quiz_history: {e}")

async def my_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        ensure_user_in_db(user)
        user_id = user.id
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            # Fetch the user's current score
            c.execute("SELECT score FROM users WHERE id = ?", (user_id,))
            score = c.fetchone()

        if score:
            await update.message.reply_text(f"Your current score is: {score[0]}")
        else:
            await update.message.reply_text("You have no score recorded.")
    except sqlite3.OperationalError as e:
        await update.message.reply_text("An error occurred with the database. Please try again later.")
        logging.error(f"Database error in my_score: {e}")

async def main() -> None:
    setup_db()
    application = Application.builder().token(TOKEN).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("user_info", user_info))
    application.add_handler(CommandHandler("set_language", set_language))
    application.add_handler(CommandHandler("my_quizzes", my_quizzes))
    application.add_handler(CommandHandler("all_users", all_users))
    application.add_handler(CommandHandler("score_history", score_history))
    application.add_handler(CommandHandler("my_score", my_score))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^/$'), show_commands))

    # Register the user update handler
    application.add_handler(MessageHandler(filters.ALL, handle_user_update))

    # Set bot commands for Telegram to display
    await application.bot.set_my_commands([
        BotCommand("start", "Initialize or reset profile"),
        BotCommand("help", "Show available commands"),
        BotCommand("quiz", "Start a quiz"),
        BotCommand("leaderboard", "See top scorers"),
        BotCommand("user_info", "Check your information"),
        BotCommand("set_language", "Change bot language"),
        BotCommand("my_quizzes", "See your quiz history"),
        BotCommand("all_users", "List all users (admin only)"),
        BotCommand("score_history", "View your score history"),
        BotCommand("my_score", "View your current score"),
        BotCommand("reset", "Reset your score to 0")
    ])

    print("Starting bot...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nBot stopped gracefully!")
    finally:
        await application.stop()

if __name__ == '__main__':
    asyncio.run(main())