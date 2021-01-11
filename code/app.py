#!/usr/local/bin/python
# -*- coding: utf-8 -*-

"""NuvlaBox Management API

This service provides a management API to the NuvlaBox,
that can be remotely and securely used from Nuvla

Arguments:

"""

import logging
import os
import subprocess
import multiprocessing
import time
import json
import nuvla
from flask import Flask, redirect, request, jsonify, url_for
from management_api.common import utils
from management_api import Manage
from threading import Thread


__copyright__ = "Copyright (C) 2020 SixSq"
__email__ = "support@sixsq.com"

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

logging.basicConfig(format='%(levelname)s - %(funcName)s - %(message)s', level='INFO')
log = logging.getLogger(__name__)


def check_authorized_keys_file():
    """ Makes the initial checks for SSH key management
    Checks if the authorized keys file exists and gives back its content and path

    :returns authorized_keys_file_content, authorized_keys_file_path: content and path of the authorized keys file"""

    authorized_keys_file = "{}/authorized_keys".format(utils.host_ssh_folder)

    if os.path.isfile(authorized_keys_file):
        with open(authorized_keys_file) as akr:
            authorized_keys = akr.read()
    else:
        authorized_keys = ''

    return authorized_keys, authorized_keys_file


def add_ssh_key(pubkey):
    """ Adds a public SSH key to the host's root authorized keys

    :param pubkey: string containing the full public key
    """

    authorized_keys, authorized_keys_file = check_authorized_keys_file()

    with open(authorized_keys_file, 'a+') as ak:
        keys = pubkey.replace('\\n', '\n').splitlines()
        for key in keys:
            if key not in authorized_keys:
                ak.write("\n{}\n".format(key))
                log.info("SSH public key added to host user {}: {}".format(utils.ssh_user, key))
            else:
                log.info("SSH public key {} already added to host. Skipping it".format(key))


def remove_ssh_key(pubkey):
    """ Removes a public SSH key from the host's authorized keys

    :param pubkey: string containing the full public key
    """

    authorized_keys, authorized_keys_file = check_authorized_keys_file()

    # in case the passed value has more than 1 public SSH key
    revoke_keys = pubkey.replace('\\n', '\n').splitlines()
    final_keys = authorized_keys.splitlines()
    for key in revoke_keys:
        if key in final_keys:
            final_keys.remove(key)

    if final_keys != authorized_keys.splitlines():
        with open(authorized_keys_file, 'w') as ak:
            ak.write("\n".join(final_keys))
        log.info("SSH public key removed from host user {}: {}".format(utils.ssh_user, pubkey))
    else:
        log.info("The provided SSH public key {} is not in the host's authorized keys. Nothing to do".format(pubkey))


def default_ssh_key():
    """ Looks for the env var NUVLABOX_SSH_PUB_KEY, and add the respective
     SSH public key to the host
    """

    if utils.provided_pubkey:
        log.info("Environment variable NUVLABOX_SSH_PUB_KEY found. Adding key to host user {}".format(utils.ssh_user))
        add_ssh_key(utils.provided_pubkey)


def wait_for_certificates():
    """ If there are already TLS credentials for the compute-api, then re-use them """

    log.info("Re-using compute-api SSL certificates for NuvlaBox Management API")
    log.info("Waiting for compute-api to generate SSL certificates...")

    while not os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.server_cert_file)) or \
            not os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.server_key_file)) or \
            not os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.ca_file)):

        time.sleep(3)


def request_stop_mjpg_streamer_container(name, nuvla_resource_id):
    log.info("Stopping container {}".format(name))
    Manage.stop_container_data_source_mjpg(name)
    try:
        log.info("Updating {} in Nuvla".format(nuvla_resource_id))
        Manage.update_peripheral_resource(nuvla_resource_id, data_gateway_enabled=False)
    except nuvla.api.api.NuvlaError as e:
        if e.response.status_code == 404:
            log.warning("Peripheral {} has already been delete in Nuvla. Nothing to do".format(nuvla_resource_id))
            # this action was triggered by the deletion of the peripheral,
            # so it's normal that it does not exist anymore
            pass
        else:
            log.exception("Could not update {} in Nuvla. Trying a second time...".format(nuvla_resource_id))
            # try again. If still fails, then raise the exception
            Manage.update_peripheral_resource(nuvla_resource_id, data_gateway_enabled=False)


def request_start_mjpg_streamer_container(name, nuvla_resource_id, device, resolution, fps):
    log.info("Launching MJPG streamer container {} for {}".format(name, device))
    local_data_gateway_endpoint, container = Manage.start_container_data_source_mjpg(name,
                                                                                     device,
                                                                                     resolution,
                                                                                     fps)
    if container.status.lower() == 'created':
        log.info("MJPG streamer {} successfully created. Updating {} in Nuvla".format(name, nuvla_resource_id))

        Manage.update_peripheral_resource(nuvla_resource_id, local_data_gateway_endpoint=local_data_gateway_endpoint)
        return True, container.logs().decode('utf-8')
    else:
        log.error("MJPG streamer {} could not be started: {}".format(name, container.status))

        return False, container.logs().decode('utf-8')


@app.errorhandler(404)
def page_not_found(e):
    # return a JSON error code, explicit
    return jsonify(dict(utils.return_404, message=str(e))), utils.return_404['status']


@app.errorhandler(405)
def method_not_allowed(e):
    # return a JSON error code, explicit
    return jsonify(dict(utils.return_405, message=str(e))), utils.return_405['status']


@app.route("/")
def root():
    # redirect to self-discovery api endpoint
    return redirect("/api", code=302)


@app.route("/api")
def self_discovery():
    # return a list of all api endpoints
    links = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint != 'static':
            url = url_for(rule.endpoint, **(rule.defaults or {}))
            links.append(url)
    return jsonify({"nuvlabox-api-endpoints": links}), 200


@app.route("/api/reboot", methods=['POST'])
def reboot():
    # reboot the host

    thread = Thread(target=Manage.reboot)
    thread.start()

    return jsonify(dict(utils.return_200, message="rebooting NuvlaBox machine...")), utils.return_200['status']


@app.route("/api/add-ssh-key", methods=['POST'])
def accept_new_ssh_key():
    # adds an SSH key into the host's authorized keys
    # the payload is the public key is, raw
    payload = request.data.decode('UTF-8')

    log.info("Received request to add public SSH key to host: {}".format(payload))

    if not payload or not isinstance(payload, str):
        return jsonify(dict(utils.return_400, message="Payload should match a valid public SSH key. Recevied: %s" %
                                                      payload)), \
               utils.return_400['status']

    try:
        add_ssh_key(payload)
        return jsonify(dict(utils.return_200, message="Added public SSH key to host: {}".format(payload))), \
               utils.return_200['status']
    except Exception as e:
        log.exception("Cannot add public SSH key to host: {}".format(e))
        if e.status_code:
            return jsonify(dict(utils.return_500, message=str(e), status=e.status_code)), e.status_code
        else:
            return jsonify(dict(utils.return_500, message=str(e))), utils.return_500['status']


@app.route("/api/revoke-ssh-key", methods=['POST'])
def revoke_ssh_key():
    # removes the SSH public key passed in the payload,
    # from the host's authorized keys
    payload = request.data.decode('UTF-8')

    log.info("Received request to revoke public SSH key from host: {}".format(payload))

    if not payload or not isinstance(payload, str):
        return jsonify(dict(utils.return_400, message="Payload should match a valid public SSH key. Recevied: %s" %
                                                      payload)), \
               utils.return_400['status']

    try:
        remove_ssh_key(payload)
        return jsonify(dict(utils.return_200, message="Removed SSH key from host: {}".format(payload))), \
               utils.return_200['status']
    except Exception as e:
        log.exception("Cannot revoke public SSH key from host: {}".format(e))
        if e.status_code:
            return jsonify(dict(utils.return_500, message=str(e), status=e.status_code)), e.status_code
        else:
            return jsonify(dict(utils.return_500, message=str(e))), utils.return_500['status']


@app.route("/api/data-source-mjpg/enable", methods=['POST'])
def enable_data_source_mjpg():
    # enable data gateway for mjpg
    #
    # payload looks like:
    # { "id": str, "resolution": str, "fps": int, "video-device": str }
    payload = json.loads(request.data)
    mandatory_keys = {"id", "video-device"}

    if not mandatory_keys <= set(payload.keys()):
        return jsonify(dict(utils.return_400, message="Missing mandatory attributes - %s" % mandatory_keys)), \
               utils.return_400['status']

    name = payload['id'].split("/")[-1]

    try:
        resolution = payload['resolution']
    except KeyError:
        resolution = "1280x720"

    try:
        fps = int(payload['fps'])
    except KeyError:
        fps = 15

    log.info("Received /api/data-source-mjpg/enable request with payload: {}".format(payload))

    try:
        success, container_logs = request_start_mjpg_streamer_container(name, payload['id'],
                                                                        payload['video-device'],
                                                                        resolution,
                                                                        fps)

        if success:
            return jsonify(dict(utils.return_200, message="MJPG streamer started!")), utils.return_200['status']
        else:
            return jsonify(dict(utils.return_400, message=container_logs)), utils.return_400['status']
    except Exception as e:
        log.exception("Cannot enable stream: {}".format(e))

        return jsonify(dict(utils.return_500, message=str(e))), utils.return_500['status']


@app.route("/api/data-source-mjpg/disable", methods=['POST'])
def disable_data_source_mjpg():
    # disable data gateway for mjpg
    #
    # payload looks like:
    # { "id": str }
    payload = json.loads(request.data)
    mandatory_keys = {"id"}

    if not mandatory_keys <= set(payload.keys()):
        return jsonify(dict(utils.return_400, message="Missing mandatory attributes - %s" % mandatory_keys)), \
               utils.return_400['status']

    name = payload['id'].split("/")[-1]

    log.info("Received /api/data-source-mjpg/disable request with payload: {}".format(payload))

    try:
        request_stop_mjpg_streamer_container(name, payload['id'])

        return jsonify(dict(utils.return_200, message="MJPG streamer stopped for %s" % payload['id'])), \
               utils.return_200['status']
    except Exception as e:
        log.exception("Cannot disable stream: {}".format(e))
        if e.status_code:
            return jsonify(dict(utils.return_500, message=str(e), status=e.status_code)), e.status_code
        else:
            return jsonify(dict(utils.return_500, message=str(e))), utils.return_500['status']


@app.route("/api/data-source-mjpg/restart", methods=['POST'])
def restart_data_source_mjpg():
    # restart data gateway for mjpg
    #
    # payload looks like:
    # { "id": str, "video-device": str }
    payload = json.loads(request.data)
    mandatory_keys = {"id", "video-device"}

    if not mandatory_keys <= set(payload.keys()):
        return jsonify(dict(utils.return_400, message="Missing mandatory attributes - %s" % mandatory_keys)), \
               utils.return_400['status']

    name = payload['id'].split("/")[-1]

    get_env = Manage.find_container_env_vars(name, keys=["RESOLUTION", "FPS"])
    resolution = get_env.get("RESOLUTION", "1280x720")
    fps = get_env.get("FPS", 15)

    log.info("Received /api/data-source-mjpg/restart request with payload: {}".format(payload))

    try:
        request_stop_mjpg_streamer_container(name, payload['id'])
        success, container_logs = request_start_mjpg_streamer_container(name, payload['id'],
                                                                        payload['video-device'],
                                                                        resolution,
                                                                        fps)

        if success:
            return jsonify(dict(utils.return_200, message="MJPG streamer restarted!")), utils.return_200['status']
        else:
            return jsonify(dict(utils.return_400, message=container_logs)), utils.return_400['status']
    except Exception as e:
        log.exception("Cannot restart stream (old streamer might be in a faulty state): {}".format(e))
        if e.status_code:
            return jsonify(dict(utils.return_500, message=str(e), status=e.status_code)), e.status_code
        else:
            return jsonify(dict(utils.return_500, message=str(e))), utils.return_500['status']


if __name__ == "__main__":
    """ Main """

    # Check if there is an SSH key to be added to the host
    try:
        default_ssh_key()
    except:
        # it is not critical if we can't add it, for any reason
        log.exception("Could not add NUVLABOX_SSH_PUB_KEY to the host root. Moving on and discarding the provided key")

    # Let's re-use the certificates already generated for the compute-api
    wait_for_certificates()

    log.info("Starting NuvlaBox Management API!")
    try:
        subprocess.check_output(["gunicorn", "--bind=0.0.0.0:5001", "--threads=2",
                                 "--worker-class=gthread", "--workers=1", "--reload",
                                 "--keyfile", "{}/{}".format(utils.nuvlabox_api_certs_folder, utils.server_key_file),
                                 "--certfile", "{}/{}".format(utils.nuvlabox_api_certs_folder, utils.server_cert_file),
                                 "--ca-certs", "{}/{}".format(utils.nuvlabox_api_certs_folder, utils.ca_file),
                                 "--cert-reqs", "2", "--no-sendfile",
                                 "wsgi:app"])
    except FileNotFoundError:
        log.exception("Gunicorn not available!")
        raise
    except (OSError, subprocess.CalledProcessError):
        log.exception("Failed start NuvlaBox Management API!")
        log.exception("Failed start NuvlaBox Management API!")
        raise

