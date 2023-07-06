from gevent import monkey
monkey.patch_all()

import os
import random
import subprocess
import sys
import threading
import typing as T
from flask import Flask, request, jsonify
from gevent.pywsgi import WSGIServer
from threading import Timer
from uuid import uuid4
from pydantic import BaseModel
from pydantic import Field
from src.process.run_bot import BACKEND_URL
from src.process.run_bot import BotProfile
from src.process.run_bot import execute
from src.util.osm_dir import OSM_DIR

if T.TYPE_CHECKING:
    from uuid import UUID

app = Flask(__name__)

# This will hold our subprocesses, using a unique handle for each one.
subprocesses: T.Dict["UUID", threading.Thread] = {}


LOCATION_JITTER = (0.0006, 0.0006)


class StartBotRequest(BaseModel):
    region: str
    bot_type: BotProfile
    latitude: float
    longitude: float
    speed: float = Field(default=1.5)
    duration: float = Field(default=300.0)
    broadcast_period: float = Field(default=1.0)
    repath_period: float = Field(default=5.0)
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
    )
    kwargs = {
        'silent': True
    }
    thread = threading.Thread(target=target, args=args, kwargs=kwargs)
    thread.daemon = True
    thread.start()
    # TODO: do we want to log errors?
    #subproc = subprocess.Popen([str(x) for x in cmd], stdout=open(os.devnull), stderr=open(os.devnull))
    subprocesses[handle] = thread

    # Return the handle to the client.
    return jsonify({'handle': handle}), 200


if __name__ == '__main__':
    print("Starting server")
    server = WSGIServer(('0.0.0.0', 8080), app)
    server.serve_forever()

