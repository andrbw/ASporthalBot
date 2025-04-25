import requests
from datetime import datetime, timedelta
from typing import List, Dict
import logging
from bs4 import BeautifulSoup
import re
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time

# Example slots for testing
EXAMPLE_SLOTS = [
    {
        "date": "2025-04-25",
        "start_time": "19:00",
        "end_time": "22:00",
        "duration_hours": 1
    },
    {
        "date": "2025-04-26",
        "start_time": "20:00",
        "end_time": "23:00",
        "duration_hours": 1
    }
]

class AntwerpenSportScraper:
    def __init__(self):
        """Initialize the scraper for Antwerpen sports infrastructure website."""
        self.base_url = "https://www.antwerpen.be/nl/sportinfrastructuur/zoeken"
        self.location_url = "https://www.antwerpen.be/nl/sportinfrastructuur/locatie"
        self.logger = logging.getLogger(__name__)
        
        # Set up Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")  # Set window size
        
        # Initialize the WebDriver
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)  # Wait up to 10 seconds

    def search_slots(self, query_slots: List[Dict]) -> List[Dict]:
        """
        Search for available slots on the Antwerpen sports infrastructure website.
        
        Args:
            query_slots: List of dictionaries containing date, start_time, end_time, and duration_hours
            
        Returns:
            List of dictionaries containing slot information
        """
        all_results = []
        
        for query in query_slots:
            try:
                # Parse date and time
                date = datetime.strptime(query['date'], '%Y-%m-%d')
                start_time = query['start_time']
                end_time = query['end_time']
                
                # Convert date to timestamp in milliseconds
                start_timestamp = int(date.replace(
                    hour=int(start_time.split(':')[0]),
                    minute=int(start_time.split(':')[1]),
                    second=0,
                    microsecond=0
                ).timestamp() * 1000)
                
                end_timestamp = int(date.replace(
                    hour=int(end_time.split(':')[0]),
                    minute=int(end_time.split(':')[1]),
                    second=0,
                    microsecond=0
                ).timestamp() * 1000)
                
                # Format date as DD/MM/YYYY
                formatted_date = date.strftime("%d/%m/%Y")
                
                # Prepare query parameters
                params = {
                    'sport': '2317',  # Volleyball ID
                    'from': str(start_timestamp),
                    'to': str(end_timestamp),
                    'date': formatted_date
                }
                
                # Navigate to the page
                self.driver.get(f"{self.base_url}?{'&'.join(f'{k}={v}' for k, v in params.items())}")
                self.logger.info(f"Page loaded for {date.date()} {start_time}-{end_time}")
                
                # Wait for the locations to load
                try:
                    # Wait for location search result element
                    self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.type-search-result.location"))
                    )
                    self.logger.info("Locations loaded")
                    
                    # Give a little extra time for all locations to load
                    time.sleep(2)
                    
                    # Get the page source after JavaScript execution
                    page_source = self.driver.page_source
                    
                    # Parse locations from the rendered HTML
                    locations = self._parse_locations(page_source)
                    self.logger.info(f"Found {len(locations)} locations")
                    
                    # Check each location for available slots
                    for location in locations:
                        location_id = location['id']
                        location_name = location['name']
                        self.logger.info(f"Checking slots for location: {location_name} (ID: {location_id})")
                        
                        # Navigate to the location page
                        location_params = {
                            'sport': '2317',
                            'from': str(start_timestamp),
                            'to': str(end_timestamp),
                            'date': formatted_date,
                            'location': str(location_id)
                        }
                        
                        self.driver.get(
                            f"{self.location_url}/{location_id}?{'&'.join(f'{k}={v}' for k, v in location_params.items())}"
                        )
                        
                        # Wait for the slots table to load
                        try:
                            self.wait.until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "div.reservations-timeslots-wrapper"))
                            )
                            self.logger.info("Slots table loaded")
                            
                            # Give a little extra time for all slots to load
                            time.sleep(2)
                            
                            # Parse the slots, passing the time range for filtering
                            location_slots = self._parse_available_slots(self.driver.page_source, start_time, end_time)
                            for slot in location_slots:
                                slot['location_name'] = location_name
                                slot['location_id'] = location_id
                                slot['date'] = query['date']
                                slot['start_time'] = start_time
                                slot['end_time'] = end_time
                            
                            all_results.extend(location_slots)
                            
                        except TimeoutException:
                            self.logger.error(f"Timeout waiting for slots table for location {location_name}")
                            continue
                    
                except TimeoutException:
                    self.logger.error("Timeout waiting for locations to load")
                    continue
                
            except Exception as e:
                self.logger.error(f"Error while searching for slots: {str(e)}")
                continue
        
        return all_results

    def _parse_locations(self, html_content: str) -> List[Dict]:
        """Parse the HTML response to extract location information."""
        locations = []
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find all location search result elements
            location_elements = soup.find_all('div', class_='type-search-result location')
            
            for element in location_elements:
                try:
                    # Find the link to get the location ID
                    link = element.find('a', href=re.compile(r'/sportinfrastructuur/locatie/\d+'))
                    if link:
                        location_id = link['href'].split('/')[-1]
                        # Get the location name from the link text or a nearby element
                        location_name = link.text.strip() or element.find('h3').text.strip()
                        
                        locations.append({
                            'id': location_id,
                            'name': location_name
                        })
                except Exception as e:
                    self.logger.error(f"Error parsing location element: {str(e)}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error parsing locations: {str(e)}")
        
        return locations

    def _parse_available_slots(self, html_content: str, start_time: str, end_time: str) -> List[Dict]:
        """Parse the HTML response to extract available slots information."""
        # Dictionary to store unique slots with their availability
        unique_slots = {}
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find all timeslots divs
            timeslots_divs = soup.find_all('div', class_='timeslots ng-scope')
            
            for timeslot_div in timeslots_divs:
                try:
                    # Find all slot links
                    slot_links = timeslot_div.find_all('a', class_=lambda x: x and ('slot' in x.split()))
                    
                    for link in slot_links:
                        # Extract time from the link text
                        slot_time = link.text.strip()
                        
                        # Convert times to minutes for comparison
                        def time_to_minutes(time_str):
                            hours, minutes = map(int, time_str.split(':'))
                            return hours * 60 + minutes
                        
                        slot_minutes = time_to_minutes(slot_time)
                        start_minutes = time_to_minutes(start_time)
                        end_minutes = time_to_minutes(end_time)
                        
                        # Only process slots within the requested time range
                        if start_minutes <= slot_minutes < end_minutes:
                            # Check if slot is available (not disabled)
                            is_available = 'disabled' not in link.get('class', [])
                            
                            # If slot already exists, update availability if it's available in this div
                            if slot_time in unique_slots:
                                if is_available:
                                    unique_slots[slot_time]['availability'] = True
                            else:
                                # Add new slot
                                unique_slots[slot_time] = {
                                    'time': slot_time,
                                    'availability': is_available
                                }
                except Exception as e:
                    self.logger.error(f"Error parsing timeslot div: {str(e)}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error parsing slots: {str(e)}")
        
        # Convert dictionary values to list
        return list(unique_slots.values())

    def _generate_booking_url(self, location_id: str, date: str, start_time: str, end_time: str) -> str:
        """
        Generate a booking URL for a specific location and time slot.
        
        Args:
            location_id: ID of the location
            date: Date in YYYY-MM-DD format
            start_time: Start time in HH:MM format
            end_time: End time in HH:MM format
            
        Returns:
            Booking URL with all parameters
        """
        # Convert date to DD/MM/YYYY format
        formatted_date = datetime.strptime(date, '%Y-%m-%d').strftime('%d/%m/%Y')
        
        # Convert times to timestamps
        start_dt = datetime.strptime(f"{date} {start_time}", '%Y-%m-%d %H:%M')
        end_dt = datetime.strptime(f"{date} {end_time}", '%Y-%m-%d %H:%M')
        
        start_timestamp = int(start_dt.timestamp() * 1000)
        end_timestamp = int(end_dt.timestamp() * 1000)
        
        # Generate URL with parameters
        base_url = "https://www.antwerpen.be/nl/sportinfrastructuur/locatie"
        params = {
            'sport': '2317',  # Volleyball ID
            'from': str(start_timestamp),
            'to': str(end_timestamp),
            'district': '',
            'date': formatted_date,
            'location': location_id
        }
        
        return f"{base_url}/{location_id}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

    def find_available_duration_slots(self, slots: List[Dict], duration_hours: float) -> List[Dict]:
        """
        Find continuous available slots that match the requested duration.
        
        Args:
            slots: List of 30-minute slots with their availability
            duration_hours: Duration in hours for the requested slot
            
        Returns:
            List of available slots matching the requested duration
        """
        # Convert duration to number of 30-minute slots
        duration_slots = int(duration_hours * 2)
        
        # Group slots by location
        location_slots = {}
        for slot in slots:
            location_id = slot['location_id']
            if location_id not in location_slots:
                location_slots[location_id] = {
                    'name': slot['location_name'],
                    'slots': []
                }
            location_slots[location_id]['slots'].append(slot)
        
        # Sort slots by time within each location
        for location in location_slots.values():
            location['slots'].sort(key=lambda x: x['time'])
        
        # Find continuous available slots for each location
        available_duration_slots = []
        
        for location_id, location_data in location_slots.items():
            slots = location_data['slots']
            location_name = location_data['name']
            
            # Find sequences of available slots
            current_sequence = []
            for slot in slots:
                if slot['availability']:
                    current_sequence.append(slot)
                else:
                    current_sequence = []
                
                # If we have enough consecutive available slots
                if len(current_sequence) >= duration_slots:
                    # Create a duration slot
                    start_slot = current_sequence[0]
                    last_slot = current_sequence[-1]
                    
                    # Calculate end time by adding 30 minutes to the last slot's time
                    last_time = datetime.strptime(last_slot['time'], '%H:%M')
                    end_time = (last_time + timedelta(minutes=30)).strftime('%H:%M')
                    
                    # Generate booking URL
                    booking_url = self._generate_booking_url(
                        location_id=location_id,
                        date=start_slot['date'],
                        start_time=start_slot['time'],
                        end_time=end_time
                    )
                    
                    available_duration_slots.append({
                        'location_id': location_id,
                        'location_name': location_name,
                        'date': start_slot['date'],
                        'start_time': start_slot['time'],
                        'end_time': end_time,
                        'duration_hours': duration_hours,
                        'booking_url': booking_url
                    })
                    
                    # Remove the first slot to continue searching
                    current_sequence = current_sequence[1:]
        
        return available_duration_slots

def main():
    """Test the scraper with example parameters."""
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Initialize scraper
        scraper = AntwerpenSportScraper()
        
        # Use example slots for testing
        slots = scraper.search_slots(EXAMPLE_SLOTS)
        
        # Print all 30-minute slots
        print(f"\nFound {len(slots)} 30-minute slots:")
        for slot in slots:
            print(f"\nDate: {slot['date']}")
            print(f"Time Range: {slot['start_time']}-{slot['end_time']}")
            print(f"Location: {slot['location_name']}")
            print(f"Slot Time: {slot['time']}")
            print(f"Available: {'Yes' if slot['availability'] else 'No'}")
        
        # Find available duration slots for each query
        for query in EXAMPLE_SLOTS:
            # Filter slots for this query
            query_slots = [slot for slot in slots if 
                         slot['date'] == query['date'] and
                         slot['start_time'] == query['start_time'] and
                         slot['end_time'] == query['end_time']]
            
            # Find available duration slots
            duration_slots = scraper.find_available_duration_slots(query_slots, query['duration_hours'])
            
            # Print results
            print(f"\nAvailable {query['duration_hours']}-hour slots for {query['date']} {query['start_time']}-{query['end_time']}:")
            if duration_slots:
                for slot in duration_slots:
                    print(f"\nLocation: {slot['location_name']}")
                    print(f"Time: {slot['start_time']} - {slot['end_time']}")
                    print(f"Booking URL: {slot['booking_url']}")
            else:
                print("No available slots found")
                
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        # Clean up
        scraper.driver.quit()

if __name__ == "__main__":
    main() 