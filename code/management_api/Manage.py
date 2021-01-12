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
    "data_source_mjpg": "nuvlabox/data-source-mjpg:0.0.2"
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

    try:
        existing_container = client.containers.get(name)
        if existing_container:
            # we force kill any previous container, if there's a new request for the same streamer
            existing_container.remove(force=True)
    except docker.errors.NotFound:
        # this is good, the container shouldn't exist
        pass
    except:
        # better not move forward, as it can cause zombie containers
        raise

    cmd = '--input-type input_uvc.so --device-path {} --resolution {} --fps {}'.format(video_device,
                                                                                       resolution,
                                                                                       fps)

    path_prefix = "/video/{}".format(name)

    devices = ["{}:{}".format(video_device, video_device)]

    traefik_router_name = "traefik.http.routers.mjpg-streamer-{}-router".format(name)

    labels = {"nuvlabox.component": "True",
              "nuvlabox.data-source-container": "True",
              "traefik.enable": "true",
              "{}.rule".format(traefik_router_name): "Host(`data-gateway`) && PathPrefix(`{}`)".format(path_prefix),
              "{}.entrypoints".format(traefik_router_name): "web",
              "{}.middlewares".format(traefik_router_name): "{}-mid".format(name),
              "traefik.http.services.mjpg-streamer-{}-service.loadbalancer.server.port".format(name): "8082",
              "traefik.http.middlewares.{}-mid.replacepath.path".format(name): "/"
              }

    streaming_url = 'http://data-gateway' + path_prefix + '?action=stream'
    return streaming_url, client.containers.run(data_gateway_images['data_source_mjpg'],
                                                command=cmd,
                                                detach=True,
                                                name=name,
                                                hostname=name,
                                                devices=devices,
                                                labels=labels,
                                                network="nuvlabox-shared-network",
                                                restart_policy={"Name": "always"},
                                                environment=[f"RESOLUTION={resolution}",
                                                             f"FPS={fps}",
                                                             "CRON_DATAGATEWAY_HEALTHCHECK=1"]
                                                )


def stop_container_data_source_mjpg(name):
    """ stops mjpg streamer container by name

    :param name: unique name of the container

    :returns
    """
    client = docker.from_env()

    try:
        client.containers.get(name).remove(force=True)
    except docker.errors.NotFound:
        pass


def nuvla_api():
    """ Initialize API instance """
    if os.path.exists(utils.nuvla_configuration):
        nuvla_endpoint_raw = nuvla_endpoint_insecure_raw = None
        with open(utils.nuvla_configuration) as nuvla_conf:
            for line in nuvla_conf.read().split():
                try:
                    if line and 'NUVLA_ENDPOINT=' in line:
                        nuvla_endpoint_raw = line.split('=')[-1]
                    if line and 'NUVLA_ENDPOINT_INSECURE=' in line:
                        nuvla_endpoint_insecure_raw = bool(line.split('=')[-1])
                except IndexError:
                    pass

        if nuvla_endpoint_raw and nuvla_endpoint_insecure_raw:
            api = Api(endpoint='https://{}'.format(nuvla_endpoint_raw),
                      insecure=nuvla_endpoint_insecure_raw, reauthenticate=True)
        else:
            raise Exception(f'Misconfigured Nuvla parameters in {utils.nuvla_configuration}. Cannot perform operation')
    else:
        raise Exception("NuvlaBox is not yet ready to be operated. Missing Nuvla configuration parameters")

    try:
        with open(utils.activation_flag) as a:
            user_info = json.loads(a.read())
    except FileNotFoundError:
        raise Exception("Cannot authenticate back with Nuvla")

    api.login_apikey(user_info['api-key'], user_info['secret-key'])

    return api


def find_container_env_vars(container_name, keys=None):
    """ Inspects a container and looks up its environment variables
    If the arg keys is passed, it then looks up the values for those keys. Otherwise, it returns the full env

    :param container_name: container to be inspected
    :param keys: list of env vars to look up. If not passed, it will look up the whole environment
    :returns {key1: value1, key2: value2} - a map of the provided keys and respective values in the container env
    """

    client = docker.from_env()

    insp = client.api.inspect_container(container_name)

    try:
        env = insp['Config']['Env']
    except KeyError:
        env = []

    env_map = {}
    if keys:
        for k in keys:
            try:
                var = list(filter(lambda x: f"{k}=" in x, env))[0]
                env_map[var.split("=", 1)[0]] = var.split("=", 1)[1]
            except IndexError:
                continue
    else:
        for env_var in env:
            env_map[env_var.split("=", 1)[0]] = env_var.split("=", 1)[1]

    return env_map


def update_peripheral_resource(id, local_data_gateway_endpoint=None, data_gateway_enabled=True, raw_sample=None):
    """ sends a PUT request to Nuvla to update the peripheral resource whenever a data gateway action takes place

    :param id: UUID of the peripheral resource in nuvla
    :param local_data_gateway_endpoint: data gateway url for accessing the routed data
    :param data_gateway_enabled: whether data dateway is enabled or not
    :param raw_sample: raw data sample

    :returns """

    api = nuvla_api()
    kwargs = {'select': []}

    payload = {
        "data-gateway-enabled": data_gateway_enabled
    }

    if local_data_gateway_endpoint:
        payload['local-data-gateway-endpoint'] = local_data_gateway_endpoint
    else:
        kwargs['select'].append("local-data-gateway-endpoint")

    if raw_sample:
        payload['raw-data-sample'] = raw_sample
    else:
        kwargs['select'].append("raw-data-sample")

    api._cimi_put(id, json=payload, params=kwargs)
