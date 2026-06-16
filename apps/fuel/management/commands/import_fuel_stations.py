"""
Management command to import fuel station data from CSV.

Usage:
    python manage.py import_fuel_stations /path/to/fuel-prices.csv
    
The CSV is expected to have these columns:
    OPIS Truckstop ID, Truckstop Name, Address, City, State, Rack ID, Retail Price

Duplicate truckstop_ids are handled by keeping the lowest price entry.
Stations are geocoded using Nominatim (OpenStreetMap) to obtain lat/lon coordinates.
"""

import csv
import os
import time
import logging
from urllib.parse import quote
from django.core.management.base import BaseCommand
from django.db import transaction
import requests
from apps.fuel.models import FuelStation

logger = logging.getLogger(__name__)

# Cache for geocoding results to minimize API calls
_geocode_cache = {}


def geocode_location(city: str, state: str) -> tuple:
    """
    Geocode a city/state to lat/lon using Nominatim (OpenStreetMap).
    
    Results are cached in memory during the import process to avoid
    repeated requests for the same location.
    
    Args:
        city: City name
        state: State abbreviation (e.g., 'CA', 'NY')
    
    Returns:
        Tuple of (latitude, longitude) or (None, None) on failure
    """
    cache_key = f"{city.strip().lower()},{state.strip().lower()}"
    
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]
    
    try:
        query = quote(f"{city}, {state}, USA")
        url = f"https://nominatim.openstreetmap.org/search?q={query}&format=jsonv2&limit=1"
        
        headers = {
            # 'User-Agent': 'RouteOptimizer/1.0 (assessment@example.com)',
            
            "User-Agent": "SpotterRouteOptimizer/1.0 (contact: ladisamuel00@gmail.com)"

        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data and len(data) > 0:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            _geocode_cache[cache_key] = (lat, lon)
            return (lat, lon)
        
        logger.warning(f"No geocoding results for: {city}, {state}")
        _geocode_cache[cache_key] = (None, None)
        return (None, None)
        
    except Exception as e:
        logger.error(f"Geocoding error for {city}, {state}: {e}")
        _geocode_cache[cache_key] = (None, None)
        return (None, None)


class Command(BaseCommand):
    help = 'Import fuel station data from CSV file with geocoding'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Path to the fuel prices CSV file'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before import'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Delay between geocoding requests (seconds) to respect rate limits'
        )
        parser.add_argument(
            '--skip-geocode',
            action='store_true',
            help='Skip geocoding (use 0,0 for all coordinates)'
        )

    def handle(self, *args, **options):
        csv_path = options['csv_file']
        clear = options['clear']
        delay = options['delay']
        skip_geocode = options['skip_geocode']

        if not os.path.exists(csv_path):
            self.stderr.write(self.style.ERROR(f"File not found: {csv_path}"))
            return

        if clear:
            count, _ = FuelStation.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Cleared {count} existing stations"))

        self.stdout.write(f"Importing from {csv_path}...")

        # Read all rows and deduplicate by truckstop_id (keep lowest price)
        stations_raw = {}
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    truckstop_id = int(row['OPIS Truckstop ID'].strip())
                    price = float(row['Retail Price'].strip())
                    
                    # Keep the entry with the lowest price for each truckstop_id
                    if truckstop_id not in stations_raw or price < stations_raw[truckstop_id]['price']:
                        stations_raw[truckstop_id] = {
                            'truckstop_id': truckstop_id,
                            'name': row['Truckstop Name'].strip(),
                            'address': row['Address'].strip(),
                            'city': row['City'].strip(),
                            'state': row['State'].strip(),
                            'price': price,
                        }
                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping malformed row: {e}")
                    continue

        self.stdout.write(f"Found {len(stations_raw)} unique stations after deduplication")

        # Geocode locations (or use placeholders)
        station_objects = []
        geocoded_count = 0
        failed_count = 0
        
        unique_locations = set()
        for data in stations_raw.values():
            unique_locations.add((data['city'], data['state']))
        
        self.stdout.write(f"Geocoding {len(unique_locations)} unique locations...")
        
        # Pre-geocode all unique locations
        location_coords = {}
        if not skip_geocode:
            for i, (city, state) in enumerate(unique_locations, 1):
                lat, lon = geocode_location(city, state)
                location_coords[(city, state)] = (lat, lon)
                if lat is not None:
                    geocoded_count += 1
                else:
                    failed_count += 1
                
                if i % 10 == 0:
                    self.stdout.write(f"  Geocoded {i}/{len(unique_locations)}...")
                
                # Respect Nominatim rate limit (1 request per second recommended)
                time.sleep(delay)
        
        self.stdout.write(
            f"Geocoding complete: {geocoded_count} success, {failed_count} failed"
        )

        # Build station objects
        for data in stations_raw.values():
            if skip_geocode:
                lat, lon = 0.0, 0.0
            else:
                lat, lon = location_coords.get((data['city'], data['state']), (0.0, 0.0))
            
            station = FuelStation(
                truckstop_id=data['truckstop_id'],
                name=data['name'],
                address=data['address'],
                city=data['city'],
                state=data['state'],
                latitude=lat if lat is not None else 0.0,
                longitude=lon if lon is not None else 0.0,
                retail_price=data['price'],
            )
            station_objects.append(station)

        # Bulk create in batches
        batch_size = 500
        created_count = 0
        
        with transaction.atomic():
            for i in range(0, len(station_objects), batch_size):
                batch = station_objects[i:i + batch_size]
                FuelStation.objects.bulk_create(batch, batch_size=batch_size)
                created_count += len(batch)

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully imported {created_count} fuel stations "
                f"({geocoded_count} with coordinates, {failed_count} without)"
            )
        )
        
        if failed_count > 0 and not skip_geocode:
            self.stdout.write(
                self.style.WARNING(
                    "Some stations could not be geocoded. "
                    "Consider running with --skip-geocode for testing, "
                    "or verify the city/state data quality."
                )
            )
