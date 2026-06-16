"""Custom exceptions for the route optimizer application."""


class RouteOptimizerError(Exception):
    """Base exception for all route optimizer errors."""
    status_code = 500
    default_detail = "An unexpected error occurred."

    def __init__(self, detail=None):
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class InvalidLocationError(RouteOptimizerError):
    """Raised when a location cannot be geocoded or is invalid."""
    status_code = 400
    default_detail = "The provided location could not be resolved."


class SameLocationError(RouteOptimizerError):
    """Raised when start and destination are the same."""
    status_code = 400
    default_detail = "Start and destination locations cannot be the same."


class NoRouteError(RouteOptimizerError):
    """Raised when OSRM cannot find a drivable route."""
    status_code = 404
    default_detail = "No drivable route found between the specified locations."


class NoFuelStationError(RouteOptimizerError):
    """Raised when no fuel stations are reachable within range."""
    status_code = 422
    default_detail = "No reachable fuel stations found along the route."


class EmptyDatasetError(RouteOptimizerError):
    """Raised when the fuel station dataset is empty."""
    status_code = 503
    default_detail = "Fuel station dataset is currently unavailable."


class RoutingAPIError(RouteOptimizerError):
    """Raised when the routing API fails after retries."""
    status_code = 503
    default_detail = "Routing service is temporarily unavailable."


class CacheError(RouteOptimizerError):
    """Raised on cache backend failures."""
    status_code = 500
    default_detail = "Cache service encountered an error."
