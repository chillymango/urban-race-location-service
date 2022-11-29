"""
Subscribe to location messages and update cache
"""
import argparse
import json
import os
import random
import typing as T

import redis
from paho.mqtt import client as mqtt_client

if T.TYPE_CHECKING:
    from paho.mqtt.client import MQTTMessage

REDIS_AUTH = os.environ.get("REDIS_AUTH")


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker_address", default="3.17.24.212")
    parser.add_argument("--broker_port", type=int, default=1883)
    parser.add_argument("--redis_address", default="54.176.196.120")
    parser.add_argument("--redis_port", default=6379)
    parser.add_argument("--mqtt_user", default="mqtt-user")
    parser.add_argument("--mqtt_password", default="mqtt-password")
    parser.add_argument("--flush", action="store_true")
    return parser


def main() -> None:
    parser = get_parser()
    args = parser.parse_args()

    r_client = redis.Redis(host=args.redis_address, port=args.redis_port, db=0, password=REDIS_AUTH)
    print('setup redis')
    if args.flush:
        print('flushing db')
        r_client.flushall()
    m_client = mqtt_client.Client(f"mqtt-location-cache-{random.randint(1000, 9999)}")
    m_client.username_pw_set(args.mqtt_user, args.mqtt_password)
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)
    m_client.on_connect = on_connect
    m_client.connect(args.broker_address, args.broker_port)
    m_client.subscribe("gamestate-Location-Update")
    print('setup mqtt')

    def publish_to_redis(client, userdata, message: "MQTTMessage"):
        if not message.topic == "gamestate-Location-Update":
            return
        payload = json.loads(message.payload)
        entity = payload.get('entity')
        if entity is None:
            raise ValueError("Malformed packet - no entity")
        uuid = entity.get("uuid")
        if uuid is None:
            raise ValueError("Malformed packet - no uuid")
        device_id = entity.get("device_id")
        if device_id is None:
            raise ValueError("Malformed entity - no device ID")
        r_client.set(device_id, json.dumps(entity))
        r_client.expire(device_id, 300)  # have a TTL of 5 minutes

    m_client.on_message = publish_to_redis
    print('yaeeet')
    m_client.loop_forever()


if __name__ == "__main__":
    main()
