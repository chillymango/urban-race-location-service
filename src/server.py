from gevent import monkey
monkey.patch_all()

import math
import os
import random
import subprocess
import sys
import threading
import typing as T
from flask import Flask, request, jsonify
from geopy import distance
from gevent.pywsgi import WSGIServer
from threading import Timer
from uuid import uuid4
from pydantic import BaseModel
from pydantic import Field
from src.process.run_bot import BACKEND_URL
from src.process.run_bot import BotProfile
from src.process.run_bot import execute
from src.process.run_bot import MAP_CACHE
from src.util.osm_dir import OSM_DIR

if T.TYPE_CHECKING:
    from uuid import UUID

app = Flask(__name__)

# This will hold our subprocesses, using a unique handle for each one.
subprocesses: T.Dict["UUID", threading.Thread] = {}


LOCATION_JITTER = (0.0008, 0.0008)


class StartBotRequest(BaseModel):
    region: str
    bot_type: BotProfile
    latitude: float
    longitude: float
    speed: float = Field(default=1.0)
    duration: float = Field(default=300.0)
    broadcast_period: float = Field(default=5.0)
    repath_period: float = Field(default=5.0)
    # if bot profile is single target, masquerade as single user.
    # otherwise, masquerade as team.
    masquerade_as: str = Field(default="")


@app.route('/start', methods=['POST'])
def start_subprocess():
    start_bot_request = StartBotRequest.parse_obj(request.json)

    if start_bot_request.region not in os.listdir(OSM_DIR):
        return jsonify({'error': f'invalid OSM region {start_bot_request.region}'}), 500

    # Generate a unique handle for this process.
    handle = uuid4()
    lat_start = start_bot_request.latitude + random.random() * LOCATION_JITTER[0] * (1 if random.random() > 0.5 else -1)
    lon_start = start_bot_request.longitude + random.random() * LOCATION_JITTER[1] * (1 if random.random() > 0.5 else -1)

    # Start the subprocess and save it in our dictionary.
    target = execute
    args = (
        start_bot_request.region,
        start_bot_request.bot_type,
        lat_start,
        lon_start,
        start_bot_request.duration,
        start_bot_request.broadcast_period,
        start_bot_request.speed,
        BACKEND_URL,
        start_bot_request.masquerade_as,
    )
    kwargs = {
        'silent': True
    }
    thread = threading.Thread(target=target, args=args, kwargs=kwargs)
    thread.daemon = True
    thread.start()
    # TODO: do we want to log errors?
    subprocesses[handle] = thread

    # Return the handle to the client.
    return jsonify({'handle': handle}), 200


class GetRouteRequest(BaseModel):

    speed: float = 2.0  # meters per second
    duration: float = 5 * 60 * 60.0  # five hours of travel in game time, almost certainly won't need this
    latitude: float  # starting latitude
    longitude: float  # starting longitude
    region: str = "sf_north_beach"


class Waypoint(BaseModel):
    game_time: float
    latitude: float
    longitude: float


class GetRouteResponse(BaseModel):
    nodes: T.List[Waypoint]


@app.route("/get_route", methods=["POST"])
def api_get_route():
    """
    Return a path with some parameters.
    """
    route_request = GetRouteRequest.parse_obj(request.json)
    map = MAP_CACHE.get(route_request.region)
    if map is None:
        raise ValueError(f"Invalid map {route_request.region}")

    distance_traveled = 0.0
    game_time = 0.0
    start = map.get_closest_node_to_point(route_request.latitude, route_request.longitude)
    output = []
    output.append(Waypoint(game_time=game_time, latitude=start.latitude, longitude=start.longitude))
    prev_node = start
    while game_time < route_request.duration:
        # find the next node
        next_node = map.get_random_node()
        path = map.get_shortest_route_between_points(prev_node, next_node)
        for node1, node2 in zip(path[:-1], path[1:]):
            dist = distance.distance((node1.latitude, node1.longitude), (node2.latitude, node2.longitude)).meters
            distance_traveled += dist
            time_delta = dist / route_request.speed
            game_time += time_delta
            output.append(Waypoint(game_time=game_time, latitude=node2.latitude, longitude=node2.longitude))

    return jsonify(GetRouteResponse(nodes=output).dict()), 200


if __name__ == '__main__':
    print("Starting server")
    server = WSGIServer(('0.0.0.0', 8080), app)
    server.serve_forever()

