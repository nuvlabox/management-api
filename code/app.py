#!/usr/local/bin/python
# -*- coding: utf-8 -*-

"""NuvlaBox Management API

This service provides a management API to the NuvlaBox,
that can be remotely and securely used from Nuvla

Arguments:

"""

import logging
import sys
import os
import subprocess
import multiprocessing
import time
import json
from flask import Flask, redirect, request, jsonify, url_for
from management_api.common import utils
from management_api import Manage
from threading import Thread


__copyright__ = "Copyright (C) 2020 SixSq"
__email__ = "support@sixsq.com"

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True


def set_logger():
    """ Configures logging """
    # give logger a name: app
    root = logging.getLogger("api")
    root.setLevel(logging.DEBUG)

    # log into file
    fh = logging.FileHandler("{}/{}".format(utils.data_volume, utils.log_filename))
    fh.setLevel(logging.ERROR)

    # print to console
    c_handler = logging.StreamHandler(sys.stdout)
    c_handler.setLevel(logging.DEBUG)

    # format log messages
    formatter = logging.Formatter('%(levelname)s - %(funcName)s - %(message)s')
    c_handler.setFormatter(formatter)
    fh.setFormatter(formatter)

    # add handlers
    root.addHandler(c_handler)
    root.addHandler(fh)


def generate_ssh_key():
    """ Create an SSH key, every time """

    log = logging.getLogger("api")

    log.info("Generating SSH keys for the NuvlaBox...")
    os.system("echo 'y\n' | ssh-keygen -q -t rsa -N '' -f {} >/dev/null".format(utils.ssh_key_file))
    public_key = "{}.pub".format(utils.ssh_key_file)

    if not os.path.exists(utils.ssh_key_file) or not os.path.exists(public_key):
        log.error("Cannot generate SSH key...will move on, but SSH will be unavailable until the NuvlaBox is restarted")


def wait_for_certificates():
    """ If there are already TLS credentials for the compute-api, then re-use them """

    log = logging.getLogger("api")
    log.info("Re-using compute-api SSL certificates for NuvlaBox Management API")
    log.info("Waiting for compute-api to generate SSL certificates...")

    while not os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.server_cert_file)) and \
            not os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.server_key_file)) and \
            not os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.client_cert_file)) and \
            not os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.client_key_file)) and \
            not os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.ca_file)):

        time.sleep(3)


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


@app.route("/api/data-source-mjpg/enable", methods=['POST'])
def enable_data_source_mjpg():
    # enable data gateway for mjpg
    #
    # payload looks like:
    # { "id": str, "resolution": str, "fps": int, "stream-name": str, "video-device": str }

    payload = json.loads(request.data)
    mandatory_keys = {"id", "video-device"}

    if not mandatory_keys <= set(payload.keys()):
        return jsonify(dict(utils.return_400, message="Missing mandatory attributes - %s" % mandatory_keys)), \
               utils.return_400['status']

    id = payload['id']
    try:
        name = payload['stream-name']
    except KeyError:
        name = id

    try:
        resolution = payload['resolution']
    except KeyError:
        resolution = "1280x720"

    try:
        fps = int(payload['fps'])
    except KeyError:
        fps = 15

    try:
        local_data_gateway_endpoint, container = Manage.start_container_data_source_mjpg(name,
                                                                                         payload['video-device'],
                                                                                         resolution,
                                                                                         fps)
        if container.status.lower() == 'created':
            Manage.update_peripheral_resource(id, local_data_gateway_endpoint)
        else:
            return jsonify(dict(utils.return_400, message=container.logs())), utils.return_400['status']
    except Exception as e:
        return jsonify(dict(utils.return_generic, status=e.status_code, message=str(e.explanation))), e.status_code


if __name__ == "__main__":
    """ Main """

    set_logger()
    log = logging.getLogger("api")

    # Let's re-use the certificates already generated for the compute-api
    wait_for_certificates()

    # Generate SSH key
    generate_ssh_key()

    workers = multiprocessing.cpu_count()
    logging.info("Starting NuvlaBox Management API!")
    try:
        subprocess.check_output(["gunicorn", "--bind=0.0.0.0:5001", "--threads=2",
                                 "--worker-class=gthread", "--workers={}".format(workers), "--reload",
                                 "--keyfile", "{}/{}".format(utils.nuvlabox_api_certs_folder, utils.server_key_file),
                                 "--certfile", "{}/{}".format(utils.nuvlabox_api_certs_folder, utils.server_cert_file),
                                 "--ca-certs", "{}/{}".format(utils.nuvlabox_api_certs_folder, utils.ca_file),
                                 "--cert-reqs", "2", "--no-sendfile", "--log-level", "info",
                                 "wsgi:app"])
    except FileNotFoundError:
        logging.exception("Gunicorn not available!")
        raise
    except (OSError, subprocess.CalledProcessError):
        logging.exception("Failed start NuvlaBox Management API!")
        raise

