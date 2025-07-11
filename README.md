# UPSC SSC CGL Quiz Bot

A Telegram bot that automatically sends UPSC and SSC CGL preparation quizzes to a specified channel every hour. The bot uses OpenAI's GPT model to generate unique questions and Telegram's poll feature to create interactive quizzes.

## Features

- Sends 24 quizzes per day (one quiz every hour)
- Automatically generates unique UPSC/SSC CGL related questions
- Uses Telegram's poll feature for interactive multiple-choice questions
- Provides immediate feedback with correct answers
- Runs continuously with error handling and logging

## Setup

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. The bot is configured with the following settings in `quiz_bot.py`:
   - Telegram Bot Token
   - OpenAI API Key
   - Target Channel ID

## Running the Bot

1. Start the bot by running:
   ```bash
   python quiz_bot.py
   ```

2. The bot will automatically:
   - Generate questions using OpenAI
   - Send quizzes to the specified channel every hour
   - Handle errors and continue running

## Logging

The bot logs all activities and errors to help with monitoring and debugging. Check the console output for logs.

## Note

Make sure the bot has admin privileges in the target channel to send messages and create polls.