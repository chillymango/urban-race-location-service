"""
Lets start with just running a dummy -- it doesn't move
"""
from gevent import monkey
monkey.patch_all()

import argparse
import json
import os
import random
import requests
import signal
import threading
import time
import typing as T
from collections import deque
from contextlib import contextmanager
from enum import Enum
from pydantic import BaseModel

from src.generate_routes import Map
from src.generate_routes import Node
from src.util.distance import get_delta_between_points
from src.util.distance import dist_range
from src.util.distance import meters_between_points
from src.util.mqtt import CLIENT
from src.util.osm_dir import OSM_DIR

# this is needed to fix namespacing for pickle
import sys
sys.modules['__main__'].Node = Node


BOT_ID = None
BACKEND_URL = "https://urbanrace.fugitive.link"


MAP_CACHE = {region: Map.read_from_cache(os.path.join(OSM_DIR, region, "map.gpickle")) for region in os.listdir(OSM_DIR)}


class BotProfile(int, Enum):
    STATIONARY = 0
    RAMBLE = 1
    RAMBLE_TEAM = 2
    HUNT_ROAD = 3
    HUNT_FLY = 4  # YOU ARE SOOOOO SCREWED IT'S LITERALLY A MISSILE
    DEBUG = 5  # all kinds of shit here
    FLY = 6  # this is really just ignore roads


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("region", choices=os.listdir(OSM_DIR))
    parser.add_argument("profile", choices=BotProfile, type=lambda x: BotProfile[x.upper()])
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--backend-url", default="https://urbanrace.fugitive.link")
    parser.add_argument("--speed", type=float, default=1.5)  # walking speed
    parser.add_argument("--broadcast-period", type=float, default=3.0, help="default only broadcast a location every 1s")
    parser.add_argument("--duration", type=float, help="if specified, how long to run the bot for. If not specified, run forever.")
    parser.add_argument("--repath-period", default=5.0, help="how often to recalculate trajectory")
    return parser


def map_bot_type(profile: BotProfile) -> str:
    """
    Get the bot type name from the profile

    TODO: i mean protobuf would be nice but ugh
    """
    mapping = {
        BotProfile.STATIONARY: "DUMMY",
        BotProfile.RAMBLE: "AMBIENT",
        BotProfile.HUNT_ROAD: "SEEKER",
        BotProfile.HUNT_FLY: "SEEKER",
        BotProfile.DEBUG: "DEBUG",
    }
    return mapping[profile]


def check_out_bot(profile: BotProfile, masquerade_as: str, backend_url: str) -> str:
    """
    Issue a backend request to check out a bot.

    Returns the bot ID if successful. Throws exception if not.
    """
    bot_type = map_bot_type(profile)
    resp = requests.post(f"{backend_url}/api/bots/check_out", json={'bot_type': bot_type, 'masquerade_as': masquerade_as})
    resp.raise_for_status()

    return json.loads(resp.text)["bot_id"]


def check_in_bot(bot_id: str) -> None:
    msg = dict(
        transactionId=-1,
        idsToRemove=[bot_id]
    )
    cts = 0
    while cts < 3:
        CLIENT.publish("gamestate-Location-Remove", json.dumps(msg))
        time.sleep(1.00)  # wow networking sucks
        cts += 1
    resp = requests.post(f"{BACKEND_URL}/api/bots/check_in", json={'bot_id': bot_id})
    resp.raise_for_status()


@contextmanager
def bot_context(profile: BotProfile, masquerade_as: str, backend_url: str) -> T.Iterator[str]:
    bot_id = None
    try:
        bot_id = check_out_bot(profile, masquerade_as, backend_url)
        yield bot_id
    finally:
        if bot_id is not None:
            check_in_bot(bot_id)


def fmt_location_message(client_id: str, latitude: float, longitude: float) -> T.Dict:
    return dict(
        transactionId=-1,
        entity=dict(
            uuid=client_id,
            device_id=f"BOT-{client_id}",
            timestamp=time.time(),
            pos_lat=latitude,
            pos_lon=longitude,
        )
    )


def setup_shutdown_timer(duration: T.Optional[float], off_event: threading.Event):
    if duration is None:
        return
    timer = threading.Timer(duration, off_event.set)
    timer.daemon = True
    timer.start()


def do_stationary_bot(bot_id: str, lat: float, lon: float, duration: float = None, broadcast_period: float = 1.0):
    off = threading.Event()
    setup_shutdown_timer(duration, off)

    while not off.isSet():
        msg_dict = fmt_location_message(bot_id, lat, lon)
        CLIENT.publish("gamestate-Location-Update", json.dumps(msg_dict))
        time.sleep(broadcast_period)


def do_ramble_bot(
    bot_id: str,
    map: Map,
    start_lat: float = None,
    start_lon: float = None,
    speed: float = 2.0,  # speed in meters per second
    duration: float = None,
    broadcast_period: float = 1.0,
    verbose: bool = True
):
    """
    Ramble Bot Rules:
     * strongly prefer not visiting the same spot again, but if there are no choices, it's fine.
     * ramble bots start by walking to the nearest road point
     * afterwards, ramble bots will pick a random neighbor to start traversing towards and
       set that as the next waypoint
     * when the bot closes proximity with a waypoint to within 10m, it will pick the next waypoint
       if there is one enqueued, or it will enqueue itself a new one.
    """
    def _print(msg: str) -> None:
        if verbose:
            print(msg)

    off = threading.Event()
    setup_shutdown_timer(duration, off)

    # waypoints are a double ended queue
    # traversal algorithm pops from right, can insert to left to add additional waypoints
    waypoints: T.Deque[str] = deque()

    # do not allow cycles unless there are no other options
    seen_waypoints: T.Dict[str, int] = dict()  # use node IDs to keep track

    # if we have a start point, use that
    if start_lat is not None and start_lon is not None:
        # we start by walking to the closest node to our start point
        start = map.get_closest_node_to_point(start_lat, start_lon)
        pos = (start_lat, start_lon)
        waypoints.append(start.ref_id)
    # otherwise pick a random node
    else:
        start = map.get_random_node()
        pos = (start.lat, start.lon)

    _print(f'Ramble bot proceeding to ({start.lat}, {start.lon}) first')

    # initial position, not the start route position
    node = None
    waypoint = None
    waypoint_count = 0
    while not off.isSet():

        # Enqueue New Waypoint
        if not waypoints:
            # enqueue new ramble waypoint here, typically the next neighbor node
            if node is None:  # safe to just use this usually
                node = map.get_closest_node_to_point(*pos)

            # find a new point on the map to travel to
            idx = 0
            while True:
                idx += 1
                if idx > 30:
                    # ok we give up just go next
                    node = map.get_random_node()

                new_waypoint = map.get_random_node()
                # figure out the path to that new waypoint
                path_to_new_waypoint = map.get_shortest_route_between_points(node, new_waypoint)[1:]
                if not path_to_new_waypoint:
                    _print('Warning: random point is not connected')
                    time.sleep(1.)
                    continue

                _print(f'Adding waypoints: {path_to_new_waypoint}')
                for path_point in path_to_new_waypoint:
                    waypoints.append(path_point.ref_id)
                break

        # Pop Waypoint
        if waypoint is None:
            # tell the loop to get the next waypoint
            waypoint = waypoints.popleft()
            node = map.get_node_from_id(waypoint)
            waypoint_count += 1
            seen_waypoints[waypoint] = waypoint_count
            # TODO: turn this into heading and velocity
            meters_to_start = meters_between_points(*pos, node.lat, node.lon)
            if meters_to_start == 0:
                continue
            meters_to_deg = speed * dist_range(*pos, node.lat, node.lon) / meters_to_start

            # we have a chance of stopping at this point for some period of time
            # TODO: make this configurable
            if random.random() < 0.01:
                wait = random.randint(15, 120)
                _print(f'We are taking a break here for {wait}s')
                do_stationary_bot(
                    bot_id,
                    *pos,
                    wait,
                    broadcast_period=broadcast_period
                )

        if dist_range(*pos, node.lat, node.lon) < 0.00001:
            # reached, figure out the next waypoint
            waypoint = None
            continue

        # start moving towards waypoint
        dist_moved = meters_to_deg * broadcast_period
        delta, overshoot = get_delta_between_points(dist_moved, *pos, node.lat, node.lon)
        # if we're going to overshoot target, just snap to target
        if overshoot:
            new_lat, new_lon = node.lat, node.lon
        else:
            new_lat = pos[0] + delta[0]
            new_lon = pos[1] + delta[1]

        pos = (new_lat, new_lon)

        # create message and push it
        _print(pos)
        msg_dict = fmt_location_message(bot_id, pos[0], pos[1])
        CLIENT.publish("gamestate-Location-Update", json.dumps(msg_dict))
        time.sleep(broadcast_period)


def execute(
    region: str,
    profile: BotProfile,
    latitude: float,
    longitude: float,
    duration: float,
    broadcast_period: float,
    speed: float,
    backend_url: str,
    masquerade_as: str = "",
    silent: bool = False
) -> None:
    with bot_context(profile, masquerade_as, backend_url) as bot_id:
        if profile == BotProfile.STATIONARY:
            do_stationary_bot(
                bot_id,
                latitude,
                longitude,
                duration,
                broadcast_period
            )
            return

        region_dir = os.path.join(OSM_DIR, region)
        if not os.path.exists(region_dir):
            raise OSError(f"No region files found at {region_dir}")

        if region not in MAP_CACHE:
            raise ValueError(f"No map loaded for {region}")
        map = MAP_CACHE[region]

        if profile == BotProfile.RAMBLE:
            do_ramble_bot(
                bot_id,
                map,
                latitude,
                longitude,
                speed=speed,
                duration=duration,
                broadcast_period=broadcast_period,
                verbose=not silent,
            )
        elif profile == BotProfile.RAMBLE_TEAM:
            # check out an additional bot
            # TODO: figure this out
            pass
        elif profile == BotProfile.HUNT_FLY:
            # TODO: implement
            pass
        elif profile == BotProfile.HUNT_ROAD:
            # TODO: implement
            pass
        else:
            raise ValueError(f"We don't support {profile} (yet)")


def main() -> None:
    parser = get_parser()
    args = parser.parse_args()

    global BACKEND_URL
    if args.backend_url != BACKEND_URL:
        BACKEND_URL = args.backend_url

    execute(
        args.region,
        args.profile,
        args.latitude,
        args.longitude,
        args.duration,
        args.broadcast_period,
        args.speed,
        args.backend_url
    )


if __name__ == "__main__":
    main()
