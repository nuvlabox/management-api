#!/usr/local/bin/python3.7
# -*- coding: utf-8 -*-

""" All the management functions that can be called from the API """

import os
import time
import docker
import json
from management_api.common import utils
from nuvla.api import Api

# TODO: is there a way to avoid fixing a tag? If a new tag comes out, we need to update this microservice
data_gateway_images = {
    "data_source_mjpg": "nuvlabox/data-source-mjpg:0.0.1"
}


def reboot():
    # reboot the host
    # NOTE: there's no return from this function
    time.sleep(5)
    os.system("echo b > /sysrq")


def enable_ssh():
    # TODO
    time.sleep(5)


def start_container_data_source_mjpg(name, video_device, resolution, fps):
    """ starts mjpg streamer

    :param name: unique name of the container and termination of the pathprefix in traefik
    :param video_device: path to video device, i.e. /dev/video0
    :param resolution: video feed resolution (str like WxH)
    :param fps: number of frames per second

    :returns local_data_gateway_endpoint and container obj
    """
    client = docker.from_env()

    cmd = '--input-type input_uvc.so --device-path {} --resolution {} --fps {}'.format(video_device,
                                                                                       resolution,
                                                                                       fps)

    path_prefix = "/video/{}".format(name)

    devices = ["{}:{}".format(video_device, video_device)]

    traefik_router_name = "traefik.http.routers.mjpg-streamer-{}-router".format(name)

    labels = {"nuvlabox.component": "False",
              "nuvlabox.data-source-container": "True",
              "traefik.enable": "true",
              "{}.rule".format(traefik_router_name): "Host(`data-gateway`) && PathPrefix(`{}`)".format(path_prefix),
              "{}.entrypoints".format(traefik_router_name): "web",
              "{}.middlewares".format(traefik_router_name): "{}-mid".format(name),
              "traefik.http.services.mjpg-streamer-{}-service.loadbalancer.server.port".format(name): "8082",
              "traefik.http.middlewares.{}-mid.replacepath.path".format(name): "/"
              }

    return path_prefix, client.containers.run(data_gateway_images['data_source_mjpg'],
                                              command=cmd,
                                              detach=True,
                                              name=name,
                                              devices=devices,
                                              labels=labels,
                                              network="nuvlabox-shared-network",
                                              restart_policy={"Name": "always"}
                                              )


def stop_container_data_source_mjpg(name):
    """ stops mjpg streamer container by name

    :param name: unique name of the container

    :returns
    """
    client = docker.from_env()

    client.containers.get(name).remove(force=True)


def update_peripheral_resource(id, local_data_gateway_endpoint, data_gateway_enabled=True, raw_sample=None):
    """ sends a PUT request to Nuvla to update the peripheral resource whenever a data gateway action takes place

    :param id: UUID of the peripheral resource in nuvla
    :param local_data_gateway_endpoint: data gateway url for accessing the routed data
    :param data_gateway_enabled: whether data dateway is enabled or not
    :param raw_sample: raw data sample

    :returns """

    api = Api(endpoint='https://{}'.format(utils.nuvla_endpoint),
              insecure=utils.nuvla_endpoint_insecure, reauthenticate=True)

    try:
        with open(utils.activation_flag) as a:
            user_info = json.loads(a.read())
    except FileNotFoundError:
        raise Exception("Cannot authenticate back with Nuvla")

    api.login_apikey(user_info['api-key'], user_info['secret-key'])

    payload = {
        "local-data-gateway-endpoint": local_data_gateway_endpoint,
        "data-gateway-enabled": data_gateway_enabled
    }

    if raw_sample:
        payload['raw-data-sample'] = raw_sample

    api._cimi_put(id, json=payload)
