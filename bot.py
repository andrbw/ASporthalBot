import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler

from sport_slots import parse_slot_query
from scraper import AntwerpenSportScraper
from sport_slots import parse_slot_query

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

if not TELEGRAM_TOKEN:
    raise ValueError("No TELEGRAM_TOKEN found in environment variables. Please set it in .env file")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
SEARCHING = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! 👋\n\n"
        "I can help you find free slots in sport halls.\n"
        "Use /search to start searching for available slots, or\n"
        "Use /help to see all available commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "Available commands:\n\n"
        "/search - Start searching for available slots\n"
        "Example queries:\n"
        "- find all free slots 2 hours long this weekend in time range 10:00-15:00\n"
        "- show available slots 1 hour long this weekend between 14:00-18:00\n\n"
        "/test - Test the scraper with a predefined command\n"
        "/cancel - Cancel the current operation\n"
        "/help - Show this help message"
    )
    await update.message.reply_text(help_text)

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Test the scraper with a predefined command."""
    try:
        # Load the test command
        with open('test_command.json', 'r') as f:
            command = json.load(f)
        
        # Initialize the scraper
        scraper = AntwerpenSportScraper()
        
        # Convert command to query format
        query = [{
            'date': command['date'],
            'start_time': command['start_time'],
            'end_time': command['end_time'],
            'duration_hours': command['duration_hours']
        }]
        
        # Search for slots
        slots = scraper.search_slots(query)
        
        # Find available duration slots
        duration_slots = scraper.find_available_duration_slots(slots, command['duration_hours'])
        
        # Format the response
        if not duration_slots:
            await update.message.reply_text("No available slots found for the specified time and duration.")
            return
        
        response = f"*Available {command['duration_hours']}-hour slots for {command['date']} {command['start_time']}-{command['end_time']}:*\n\n"
        
        for slot in duration_slots:
            slot_message = (
                f"🏟️ *{slot['location_name']}*\n"
                f"⏰ {slot['start_time']} - {slot['end_time']}\n"
                f"📅 {slot['date']}\n"
                f"🔗 [Book Now]({slot['booking_url']})"
            )
            response += slot_message + "\n\n"
        
        await update.message.reply_markdown(response)
        
    except Exception as e:
        logger.error(f"Error in test command: {str(e)}")
        await update.message.reply_text(f"Error processing test command: {str(e)}")
    finally:
        # Clean up
        scraper.driver.quit()

async def search_slots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the slot search conversation."""
    await update.message.reply_text(
        "Please tell me what kind of slot you're looking for.\n\n"
        "For example:\n"
        "- find all free slots 2 hours long this weekend in time range 10:00-15:00\n"
        "- show available slots 1 hour long this weekend between 14:00-18:00\n\n"
        "Type /cancel to stop searching."
    )
    return SEARCHING

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the natural language query and search for slots."""
    query = update.message.text
    
    try:
        # Initialize the scraper
        scraper = AntwerpenSportScraper()
        
        # Parse the query using LLM to get slot queries
        slot_queries = await parse_slot_query(query)
        
        # Convert slot queries to the format expected by the scraper
        query_slots = [{
            'date': slot.date.strftime('%Y-%m-%d'),
            'start_time': slot.start_time,
            'end_time': slot.end_time,
            'duration_hours': slot.duration_hours
        } for slot in slot_queries]
        
        # Search for slots
        slots = scraper.search_slots(query_slots)
        
        # Find available duration slots for each query
        all_duration_slots = []
        for query in query_slots:
            # Filter slots for this query
            query_slots = [slot for slot in slots if 
                         slot['date'] == query['date'] and
                         slot['start_time'] == query['start_time'] and
                         slot['end_time'] == query['end_time']]
            
            # Find available duration slots
            duration_slots = scraper.find_available_duration_slots(query_slots, query['duration_hours'])
            all_duration_slots.extend(duration_slots)
        
        # Format the response
        if not all_duration_slots:
            await update.message.reply_text("No available slots found for the specified time and duration.")
            return ConversationHandler.END
        
        response = "*Available slots:*\n\n"
        
        for slot in all_duration_slots:
            slot_message = (
                f"🏟️ *{slot['location_name']}*\n"
                f"⏰ {slot['start_time']} - {slot['end_time']}\n"
                f"📅 {slot['date']}\n"
                f"🔗 [Book Now]({slot['booking_url']})"
            )
            response += slot_message + "\n\n"
        
        await update.message.reply_markdown(response)
        
    except Exception as e:
        logger.error(f"Error in handle_query: {str(e)}")
        await update.message.reply_text(f"Error processing your query: {str(e)}")
    finally:
        # Clean up
        scraper.driver.quit()
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation."""
    await update.message.reply_text("Search cancelled.")
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to the user."""
    logger.error(f"Update {update} caused error {context.error}")
    if update.effective_message:
        await update.effective_message.reply_text("Sorry, an error occurred while processing your request.")

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add conversation handler for slot search
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("search", search_slots)],
        states={
            SEARCHING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_query)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(conv_handler)
    
    # Add error handler
    application.add_error_handler(error_handler)

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 