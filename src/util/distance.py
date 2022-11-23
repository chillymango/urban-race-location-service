import math
import typing as T


EARTH_RADIUS_METERS = 6371E3


def dist_range(lat0: float, lon0: float, lat1: float, lon1: float) -> float:
    return math.sqrt(math.pow(abs(lat0 - lat1), 2) + math.pow(abs(lon0 - lon1), 2))


def meters_between_points(lat0: float, lon0: float, lat1: float, lon1: float) -> float:
    lat0 = float(lat0)
    lon0 = float(lon0)
    lat1 = float(lat0)
    lon1 = float(lon1)
    phi0 = lat0 * math.pi / 180
    phi1 = lat1 * math.pi / 180
    dphi = (lat1 - lat0) * math.pi / 180
    dlam = (lon1 - lon0) * math.pi / 180

    a = (
        math.sin(dphi / 2) * math.sin(dphi / 2)
        + math.cos(phi0) * math.cos(phi1) * math.sin(dlam / 2) * math.sin(dlam / 2)
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_METERS * c


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
