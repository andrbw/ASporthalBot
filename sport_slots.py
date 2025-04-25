from datetime import datetime, timedelta
import re
from bs4 import BeautifulSoup
import requests
from typing import Optional, Tuple
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get OpenAI API key from environment variables
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("No OPENAI_API_KEY found in environment variables. Please set it in .env file")

class SlotQuery(BaseModel):
    """Query parameters for slot search."""
    duration_hours: Optional[float] = Field(None, description="Duration of the slot in hours (with 30-min granularity)")
    date: Optional[datetime] = Field(None, description="Date of the event")
    start_time: Optional[str] = Field(None, description="Start time in HH:MM format")
    end_time: Optional[str] = Field(None, description="End time in HH:MM format")

class SlotArray(BaseModel):
    """Array of slot queries."""
    slots: list[SlotQuery] = Field(..., description="List of slot queries")

def parse_time(time_str: str) -> Optional[timedelta]:
    """Convert time string to timedelta."""
    try:
        hours, minutes = map(int, time_str.split(':'))
        return timedelta(hours=hours, minutes=minutes)
    except:
        return None

def parse_date(date_str: str) -> Optional[datetime]:
    """Convert date string to datetime."""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except:
        return None

async def parse_natural_query(query: str) -> list[SlotQuery]:
    """Parse natural language query using OpenAI GPT."""
    # Get current date
    today = datetime.now()
    current_date = today.strftime("%d/%m/%Y, %A")
    
    # Initialize the OpenAI model
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0,
        api_key=OPENAI_API_KEY,
        streaming=False
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", '''You are a helpful assistant that extracts slot booking information from natural language queries. This information will be used by scrapper script to fill the form on a booking website. The form has the following fields: date, start time, end time, and sport. Once the form is submitted, the website shows the list of available slots with granularity 30 minutes. The earliest slot is 8:30-9:00, the latest slot is 22:30-23:00.

TASK:
Extract the values for the website form from the natural language query and return a JSON array of slot objects. 

DATE HANDLING:
- Calculate all dates relative to today {current_date}
- Common date patterns:
  * "next weekend" = upcoming Saturday and Sunday
  * "this week Sunday" = Sunday of current week
  * "next week Sunday" = Sunday of next week
  * "tomorrow" = day after today
  * "next week" = 7 days from today
  * "this weekend" = upcoming Saturday and Sunday
- Format dates as YYYY-MM-DD

TIME HANDLING:
- Convert times to 24-hour format (e.g., "2 PM" -> "14:00") 
- Time ranges: specify both start_time and end_time
- Single time: use as start_time

- Common time patterns: 
  * "morning" = slot starts between 09:00 and 11:30
  * "evening" = slot starts between 19:00 and 22:30
  * "afternoon" = slot starts between 12:00 and 14:00 
- Format times as HH:MM

SLOT OBJECT STRUCTURE:
Each slot object must have these fields:
- duration_hours (number or null): Duration in hours (with 30-min granularity) of a full session user is looking for
- date (YYYY-MM-DD): Date of the event that will be set in the form on the website 
- start_time (HH:MM): Start time that will be set in the form on the website 
- end_time (HH:MM): End time that will be set in the form on the website 

JSON ARRAY FORMAT:
- Return a single JSON array containing one or more slot objects
- Each slot object should be enclosed in curly braces {{}}
- Objects should be separated by commas
- The entire array should be enclosed in square brackets []

IMPORTANT:
- Return ONLY the JSON array, no additional text
- Calculate dates and times from the query
- Handle multiple slots if specified
- Set unspecified information to null
'''),
        ("human", "{input}")
    ])

    # Format the messages with both variables at once
    formatted_prompt = prompt.format_messages(current_date=current_date, input=query)
    
    print("--------------Formatted prompt: ", formatted_prompt)
    
    # Get response from LLM
    response = await llm.ainvoke(formatted_prompt)
    
    print("--------------Full response from LLM: ", response)
    print("--------------Response type: ", type(response))
    print("--------------Response length: ", len(str(response)))
    
    # Handle both string and object responses
    response_text = response.content if hasattr(response, 'content') else response
    
    try:
        # Clean up the response text
        response_text = response_text.strip()
        # Remove any text before the first [ and after the last ]
        start_idx = response_text.find('[')
        end_idx = response_text.rfind(']') + 1
        if start_idx != -1 and end_idx != 0:
            response_text = response_text[start_idx:end_idx]
        
        # Parse the response into a SlotArray
        slot_array = SlotArray.parse_raw('{"slots":' + response_text + '}')
        return slot_array.slots
    except Exception as e:
        print(f"Error parsing LLM response: {e}")
        print(f"Response text: {response_text}")
        raise

def merge_slots(slots: list[SlotQuery]) -> list[SlotQuery]:
    """Merge overlapping and consecutive slots into continuous time ranges."""
    if not slots:
        return []
    
    # Sort slots by date and start time
    sorted_slots = sorted(slots, key=lambda x: (x.date, x.start_time))
    
    merged_slots = []
    current_slot = sorted_slots[0]
    
    for next_slot in sorted_slots[1:]:
        # If same date and times overlap or are consecutive
        if (current_slot.date == next_slot.date and 
            (current_slot.end_time >= next_slot.start_time or 
             datetime.strptime(current_slot.end_time, "%H:%M") + timedelta(minutes=30) == 
             datetime.strptime(next_slot.start_time, "%H:%M"))):
            # Update end time to the later of the two
            if datetime.strptime(next_slot.end_time, "%H:%M") > datetime.strptime(current_slot.end_time, "%H:%M"):
                current_slot.end_time = next_slot.end_time
        else:
            merged_slots.append(current_slot)
            current_slot = next_slot
    
    # Add the last slot
    merged_slots.append(current_slot)
    return merged_slots

async def parse_slot_query(query: str) -> list[SlotQuery]:
    """Parse natural language query into slot query objects using LLM."""
    try:
        # Parse the query using LLM
        slot_queries = await parse_natural_query(query)
        
        # Merge overlapping and consecutive slots
        merged_slots = merge_slots(slot_queries)
        
        return merged_slots
    except Exception as e:
        raise Exception(f"Error parsing slot query: {str(e)}")

async def test_slot_search(example_slots: list[SlotQuery]):
    """Test the slot search functionality with example slots."""
    print("Testing slot search with example slots")
    print("-" * 50)
    
    # Merge overlapping and consecutive slots
    merged_slots = merge_slots(example_slots)
    
    # Print results
    print("Original slots:")
    for slot in example_slots:
        print(f"- {slot.date.strftime('%Y-%m-%d')} from {slot.start_time} to {slot.end_time}")
    
    print("\nMerged slots:")
    for slot in merged_slots:
        print(f"- {slot.date.strftime('%Y-%m-%d')} from {slot.start_time} to {slot.end_time}")
    print("-" * 50)

if __name__ == "__main__":
    import asyncio
    
    # Example slots for testing (as if returned by LLM)
    example_slots = [
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-04", "%Y-%m-%d"), start_time="19:00", end_time="20:30"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-04", "%Y-%m-%d"), start_time="19:30", end_time="21:00"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-04", "%Y-%m-%d"), start_time="20:00", end_time="21:30"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-04", "%Y-%m-%d"), start_time="20:30", end_time="22:00"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-04", "%Y-%m-%d"), start_time="21:00", end_time="22:30"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-11", "%Y-%m-%d"), start_time="19:00", end_time="20:30"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-11", "%Y-%m-%d"), start_time="19:30", end_time="21:00"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-11", "%Y-%m-%d"), start_time="20:00", end_time="21:30"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-11", "%Y-%m-%d"), start_time="20:30", end_time="22:00"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-11", "%Y-%m-%d"), start_time="21:00", end_time="22:30"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-18", "%Y-%m-%d"), start_time="19:00", end_time="20:30"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-18", "%Y-%m-%d"), start_time="19:30", end_time="21:00"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-18", "%Y-%m-%d"), start_time="20:00", end_time="21:30"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-18", "%Y-%m-%d"), start_time="20:30", end_time="22:00"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-18", "%Y-%m-%d"), start_time="21:00", end_time="22:30"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-25", "%Y-%m-%d"), start_time="19:00", end_time="20:30"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-25", "%Y-%m-%d"), start_time="19:30", end_time="21:00"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-25", "%Y-%m-%d"), start_time="20:00", end_time="21:30"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-25", "%Y-%m-%d"), start_time="20:30", end_time="22:00"),
        SlotQuery(duration_hours=1.5, date=datetime.strptime("2025-05-25", "%Y-%m-%d"), start_time="21:00", end_time="22:30")
    ]
    
    asyncio.run(test_slot_search(example_slots)) 