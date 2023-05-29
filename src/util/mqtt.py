"""COPY PASTA MQTT"""
import gevent
from gevent import monkey
monkey.patch_all()

import random
import threading
from paho.mqtt import client as mqtt_client
from paho.mqtt.client import _socketpair_compat


def init_client(broker="13.56.212.128", port=1883) -> mqtt_client.Client:
    client = mqtt_client.Client(
        client_id=f"mqtt-publish-task-claims-{random.randint(1000, 10000)}"
    )
    client.username_pw_set("mqtt-user", "mqtt-password")
    client.connect(broker, port)
    client.loop_start()
    print(f'MQTT client connected at {broker}:{port}')
    return client


CLIENT = init_client()


def publish_with_retries(
    topic: str,
    payload: str,
    publishes: int = 1,
    retain: bool = True,
    qos: int = 0,
    retries: int = 0,
    broker: str = None,
    port: int = None
) -> bool:
    global CLIENT

    total_publish = 0
    if retries < 0:
        return False
    try:
        kwargs = dict()
        if broker is not None:
            kwargs['broker'] = broker
        if port is not None:
            kwargs['port'] = port
        while total_publish < publishes:
            #client.publish(topic, payload, qos=qos, retain=retain)
            CLIENT.publish(topic, payload, qos=qos, retain=retain)
            total_publish += 1
        return True
    except Exception as exc:
        print(repr(exc))
        CLIENT = init_client()
        publish_with_retries(
            topic,
            payload,
            retain=retain,
            qos=qos,
            retries=retries - 1,
            broker=broker,
            port=port
        )
