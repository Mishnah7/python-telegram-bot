# Quiz Telegram Bot

A Telegram bot that provides interactive quizzes using the Open Trivia Database API. Users can test their knowledge across various categories with multiple-choice questions.

## Features
- Multiple choice questions from various categories
- Score tracking and leaderboard
- User statistics and quiz history
- Multi-language support (English, Spanish, French)
- Daily quiz scheduling
- Admin commands for user management

## Requirements
- Python 3.7+
- Dependencies listed in `requirements.txt`

## Environment Variables
The following environment variables need to be set:
- `BOT_TOKEN`: Your Telegram Bot Token from BotFather

## Local Development
1. Clone the repository:
```bash
git clone https://github.com/Mishnah7/python-telegram-bot.git
cd python-telegram-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your bot token:
```
BOT_TOKEN=your_bot_token_here
```

4. Run the bot:
```bash
python main.py
```

## Deployment on Render
1. Fork this repository
2. Create a new Web Service on Render
3. Connect your GitHub repository
4. Configure the service:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python main.py`
   - Add environment variable: `BOT_TOKEN`
5. Deploy the service

## Database
The bot uses SQLite for data storage. Tables are automatically verified on startup:
- users: Store user information and scores
- quizzes: Track quiz questions and answers
- score_history: Record score changes
- user_audit: Track username changes