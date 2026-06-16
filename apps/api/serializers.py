 
from rest_framework import serializers
from utils.exceptions import SameLocationError


class RouteOptimizeRequestSerializer(serializers.Serializer):
 
    start = serializers.CharField(
        max_length=200,
        trim_whitespace=True,
        help_text="Start location (e.g., 'New York, United States')"
    )
    destination = serializers.CharField(
        max_length=200,
        trim_whitespace=True,
        help_text="Destination location (e.g., 'Miami, Miami-Dade County, Florida, United States')"
    )
    
    def validate(self, data):
        start = data.get('start', '').strip().lower()
        destination = data.get('destination', '').strip().lower()
        
        if start == destination:
            raise serializers.ValidationError(
                {"destination": "Start and destination cannot be the same."}
            )
        
        return data


class FuelStopSerializer(serializers.Serializer):
    station_name = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    price = serializers.DecimalField(max_digits=5, decimal_places=3)
    distance_from_start = serializers.FloatField()


class RouteOptimizeResponseSerializer(serializers.Serializer):

    start = serializers.CharField()
    destination = serializers.CharField()
    distance_miles = serializers.FloatField()
    duration_seconds = serializers.IntegerField()
    fuel_stops = FuelStopSerializer(many=True)
    estimated_total_fuel_cost = serializers.DecimalField(max_digits=8, decimal_places=2)
    route_geometry = serializers.CharField(
        help_text="Google-encoded polyline string"
    )