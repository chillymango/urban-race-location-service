import math
import typing as T
from geopy import distance


EARTH_RADIUS_METERS = 6371E3


def dist_range(lat0: float, lon0: float, lat1: float, lon1: float) -> float:
    return distance.distance((lat0, lon0), (lat1, lon1)).meters


def meters_between_points(lat0: float, lon0: float, lat1: float, lon1: float) -> float:
    return distance.distance((lat0, lon0), (lat1, lon1)).meters


def get_delta_between_points(dist: float, lat0: float, lon0: float, lat1: float, lon1: float) -> T.Tuple[float, float]:
    """
    Go a distance between start (lat0, lon0) and end (lat1, lon1). The magnitude must match.
    """
    dlat = lat1 - lat0
    dlon = lon1 - lon0
    mag = dist_range(lat0, lon0, lat1, lon1)
    return (dlat / mag * dist, dlon / mag * dist), dist > mag


def test() -> None:
    p1 = "37.547293", "-122.323097"
    p2 = "37.539892", "-122.313752"
    print(meters_between_points(*p1, *p2))


if __name__ == "__main__":
    test()
