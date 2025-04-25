# Sport Hall Booking Bot

A Telegram bot that helps you find available slots in sport halls.

## Setup Instructions

1. Clone this repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the project root with your API tokens:
   ```
   TELEGRAM_TOKEN=your_bot_token_here
   OPENAI_API_KEY=your_openai_api_key_here
   ```
5. Configure the target website URL and scraping logic in `scraper.py`
6. Run the bot:
   ```bash
   python bot.py
   ```

## Getting API Tokens

### Telegram Bot Token
1. Open Telegram and search for "@BotFather"
2. Start a chat with BotFather and send the command `/newbot`
3. Follow the instructions to create your bot
4. Copy the API token provided by BotFather and add it to your `.env` file

### OpenAI API Key
1. Go to [OpenAI's website](https://platform.openai.com/)
2. Sign up or log in to your account
3. Navigate to the API keys section
4. Create a new API key
5. Copy the API key and add it to your `.env` file

## Available Commands

- `/start` - Start the bot and get a welcome message
- `/help` - Show available commands
- `/search` - Search for available slots
- `/settings` - Configure your search preferences

## Customization

To adapt this bot for your specific sport hall booking website:

1. Modify the `SportHallScraper` class in `scraper.py` to implement the scraping logic for your target website
2. Update the search parameters and filtering options in the bot's settings
3. Customize the message templates in `bot.py` as needed

## Contributing

Feel free to submit issues and enhancement requests! 