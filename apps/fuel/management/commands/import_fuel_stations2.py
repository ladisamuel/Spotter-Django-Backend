"""
Management command to import fuel station data from CSV.
Skips geocoding for stations that already have valid coordinates.
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

_geocode_cache = {}


def geocode_location(city: str, state: str, delay: float = 1.0) -> tuple:
    """
    Geocode city/state to (lat, lon) using Nominatim.
    Returns (None, None) on failure.
    Sleeps only when an actual API call is made.
    """
    cache_key = f"{city.strip().lower()},{state.strip().lower()}"
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]

    try:
        query = quote(f"{city}, {state}, USA")
        url = f"https://nominatim.openstreetmap.org/search?q={query}&format=jsonv2&limit=1"
        headers = {"User-Agent": "SpotterRouteOptimizer/1.0 (contact: b2bdatabasesaas@gmail.com)"}

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            _geocode_cache[cache_key] = (lat, lon)
            time.sleep(delay)  # respect rate limit
            return (lat, lon)

        logger.warning(f"No geocoding results for: {city}, {state}")
        _geocode_cache[cache_key] = (None, None)
        return (None, None)

    except Exception as e:
        logger.error(f"Geocoding error for {city}, {state}: {e}")
        _geocode_cache[cache_key] = (None, None)
        return (None, None)


def has_valid_coords(lat, lon) -> bool:
    """Return True if lat/lon are not None and not zero (placeholder)."""
    return lat is not None and lon is not None and lat != 0.0 and lon != 0.0


class Command(BaseCommand):
    help = 'Import fuel stations from CSV, update existing, geocode only when missing'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str)
        parser.add_argument('--clear', action='store_true', help='Delete all existing stations before import')
        parser.add_argument('--delay', type=float, default=1.0, help='Seconds between geocoding API calls')
        parser.add_argument('--skip-geocode', action='store_true', help='Use (0,0) for all coordinates')
        parser.add_argument('--update-missing', action='store_true', default=True,
                            help='Geocode and update existing stations with missing coordinates (default: True)')

    def handle(self, *args, **options):
        csv_path = options['csv_file']
        clear = options['clear']
        delay = options['delay']
        skip_geocode = options['skip_geocode']
        update_missing = options['update_missing']

        if not os.path.exists(csv_path):
            self.stderr.write(self.style.ERROR(f"File not found: {csv_path}"))
            return

        if clear:
            count, _ = FuelStation.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Cleared {count} existing stations"))

        # Load existing stations into a dict: {truckstop_id: station_object}
        existing_stations = {s.truckstop_id: s for s in FuelStation.objects.all()}
        self.stdout.write(f"Found {len(existing_stations)} existing stations in database")

        # Read and deduplicate CSV rows (keep lowest price per truckstop_id)
        stations_raw = {}
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    truckstop_id = int(row['OPIS Truckstop ID'].strip())
                    price = float(row['Retail Price'].strip())
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

        total = len(stations_raw)
        self.stdout.write(f"Found {total} unique stations after deduplication")

        processed = 0
        created = 0
        updated = 0
        skipped = 0
        geocoded = 0
        failed_geocode = 0

        for idx, (truckstop_id, data) in enumerate(stations_raw.items(), 1):
            existing = existing_stations.get(truckstop_id)
            need_geocode = False
            lat = lon = None

            if existing and has_valid_coords(existing.latitude, existing.longitude):
                # Already has good coordinates → keep them
                lat, lon = existing.latitude, existing.longitude
                skipped += 1
                self.stdout.write(f"[{idx}/{total}] Station {truckstop_id}: exists with coords, skipped.")
            else:
                # Need coordinates: either new station or existing with missing coords
                if skip_geocode:
                    lat, lon = 0.0, 0.0
                    geocoded += 1  # treat as success for counting
                else:
                    lat, lon = geocode_location(data['city'], data['state'], delay=delay)
                    if lat is not None:
                        geocoded += 1
                    else:
                        failed_geocode += 1
                        lat, lon = 0.0, 0.0  # fallback

                if existing and update_missing:
                    # Update existing record with new coordinates and possibly updated price
                    existing.name = data['name']
                    existing.address = data['address']
                    existing.city = data['city']
                    existing.state = data['state']
                    existing.retail_price = data['price']
                    existing.latitude = lat if lat is not None else 0.0
                    existing.longitude = lon if lon is not None else 0.0
                    existing.save()
                    updated += 1
                    self.stdout.write(f"[{idx}/{total}] Station {truckstop_id}: updated with geocoded coords.")
                elif not existing:
                    # Create new record
                    FuelStation.objects.create(
                        truckstop_id=data['truckstop_id'],
                        name=data['name'],
                        address=data['address'],
                        city=data['city'],
                        state=data['state'],
                        latitude=lat if lat is not None else 0.0,
                        longitude=lon if lon is not None else 0.0,
                        retail_price=data['price'],
                    )
                    created += 1
                    self.stdout.write(f"[{idx}/{total}] Station {truckstop_id}: created with {'geocoded' if lat else 'placeholder'} coords.")
                else:
                    # existing but update_missing=False → skip
                    skipped += 1

            processed += 1
            if idx % 20 == 0 or idx == total:
                self.stdout.write(f"Progress: {idx}/{total} | Created: {created} | Updated: {updated} | Skipped: {skipped} | Geocoded: {geocoded} | Failed: {failed_geocode}")

        self.stdout.write(self.style.SUCCESS(
            f"Import complete. Processed: {processed} | "
            f"Created: {created} | Updated: {updated} | Skipped: {skipped}\n"
            f"Geocoding: {geocoded} success, {failed_geocode} failed (used 0,0)."
        ))

        if failed_geocode > 0 and not skip_geocode:
            self.stdout.write(self.style.WARNING(
                "Some stations could not be geocoded. They were inserted with (0,0). "
                "Run with --skip-geocode to avoid API calls, or check city/state data."
            ))
            
            
            
