from gevent import monkey
monkey.patch_all()

import os
import random
import subprocess
import sys
import typing as T
from flask import Flask, request, jsonify
from gevent.pywsgi import WSGIServer
from threading import Timer
from uuid import uuid4
from pydantic import BaseModel
from pydantic import Field
from src.process.run_bot import BotProfile
from src.util.osm_dir import OSM_DIR

if T.TYPE_CHECKING:
    from uuid import UUID

app = Flask(__name__)

# This will hold our subprocesses, using a unique handle for each one.
subprocesses: T.Dict[UUID, subprocess.Popen] = {}


LOCATION_JITTER = (0.0003, 0.0003)


class StartBotRequest(BaseModel):
    region: str
    bot_type: BotProfile
    latitude: float
    longitude: float
    speed: float = Field(default=1.5)
    duration: float = Field(default=300.0)
    broadcast_period: float = Field(default=1.0)
    repath_period: float = Field(default=5.0)


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
    cmd = [
        sys.executable,
        "src/process/run_bot.py",
        start_bot_request.region,
        start_bot_request.bot_type.name.upper()
    ]
    cmd.extend(["--latitude", lat_start, "--longitude", lon_start])
    cmd.extend(["--speed", start_bot_request.speed])
    cmd.extend(["--duration", start_bot_request.duration])
    cmd.extend(["--broadcast-period", start_bot_request.broadcast_period])
    cmd.extend(["--repath-period", start_bot_request.repath_period])
    print(cmd)
    # TODO: do we want to log errors?
    subproc = subprocess.Popen([str(x) for x in cmd], stdout=open(os.devnull), stderr=open(os.devnull))
    subprocesses[handle] = subproc

    # Return the handle to the client.
    return jsonify({'handle': handle}), 200


@app.route('/terminate', methods=['POST'])
def terminate_route():
    handle = request.json.get('handle')
    if handle is None:
        return jsonify({'error': 'handle not provided'}), 400
    
    result = terminate_subprocess(handle)
    
    if result == 'success':
        return jsonify({'result': 'success'}), 200
    else:
        return jsonify({'result': 'failure', 'error': 'No such process'}), 404

def terminate_subprocess(handle):
    # Get the subprocess from our dictionary and terminate it.
    proc = subprocesses.get(handle)
    if proc is None:
        return 'failure'
    
    proc.terminate()
    # remove terminated process from our dictionary
    del subprocesses[handle]

    return 'success'


if __name__ == '__main__':
    print("Starting server")
    try:
        server = WSGIServer(('0.0.0.0', 8080), app)
        server.serve_forever()
    finally:
        for process in subprocesses.values():
            try:
                process.terminate()
            except Exception as exc:
                print(f"Encountered exception during process termination: {repr(exc)}")
