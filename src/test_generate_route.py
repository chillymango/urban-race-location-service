import requests

from pydantic import BaseModel
from pydantic import Field


class GetRouteRequest(BaseModel):

    speed: float = 2.0  # meters per second
    duration: float = 5 * 60 * 60.0  # five hours of travel in game time, almost certainly won't need this
    latitude: float  # starting latitude
    longitude: float  # starting longitude
    region: str = "sf_north_beach"


def main() -> None:
    request = GetRouteRequest(
        latitude=37.80343755635129,
        longitude=-122.40794651273026
    )
    resp = requests.post("http://localhost:8080/get_route", json=request.dict())
    resp.raise_for_status()
    import pdb; pdb.set_trace()


if __name__ == "__main__":
    main()
