"""Fuel station data model with conditional spatial indexing."""

from django.conf import settings
from django.db import models

if not settings.DEBUG:
    from django.contrib.gis.db import models as gis_models


class FuelStation(models.Model):
    """
    Represents a fuel station with geospatial data.
    
    In production (DEBUG=False), a GiST spatial index is created on the
    geometry field for efficient nearest-neighbor and within-distance queries.
    In development (DEBUG=True), standard B-tree indexes on lat/lon are used.
    """
    truckstop_id = models.IntegerField(db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True, db_index=True)
    state = models.CharField(max_length=2, db_index=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, db_index=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, db_index=True)
    retail_price = models.DecimalField(max_digits=6, decimal_places=4)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Production-only PostGIS geometry field
    if not settings.DEBUG:
        location = gis_models.PointField(
            srid=4326,  # WGS 84
            spatial_index=True,
            null=True,
            blank=True
        )

    class Meta:
        db_table = 'fuel_stations'
        indexes = [
            models.Index(fields=['state', 'retail_price']),
            models.Index(fields=['latitude', 'longitude']),
        ]
        # In production, the GiST spatial index is automatically created
        # by the PointField(spatial_index=True) declaration above

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) - ${self.retail_price}"

    def save(self, *args, **kwargs):
        """Auto-populate the PostGIS geometry field in production."""
        if not settings.DEBUG and self.location is None:
            from django.contrib.gis.geos import Point
            self.location = Point(
                float(self.longitude),
                float(self.latitude),
                srid=4326
            )
        super().save(*args, **kwargs)

    @property
    def lat(self) -> float:
        """Return latitude as float."""
        return float(self.latitude)

    @property
    def lon(self) -> float:
        """Return longitude as float."""
        return float(self.longitude)

    @property
    def price(self) -> float:
        """Return retail price as float."""
        return float(self.retail_price)
