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


def generate_certificates():
    """ Generates self signed certificate """

    log = logging.getLogger("api")

    if os.path.exists(utils.nuvlabox_api_certs_folder):
        # it already exists, then just check of the certificates
        if os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.server_cert_file)) and \
                os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.server_key_file)) and \
                os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.client_cert_file)) and \
                os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.client_key_file)) and \
                os.path.exists("{}/{}".format(utils.nuvlabox_api_certs_folder, utils.ca_file)):
            # if all certificated already exist, then we are good...this was just a soft restart
            log.info("NuvlaBox API certificates already exist.")
            return
        else:
            # somehow not all certs are there...let's rebuild them all from scratch

            log.warning("Re-generating all NuvlaBox API certificates...")
    else:
        os.mkdir(utils.nuvlabox_api_certs_folder)
        log.info("Generating NuvlaBox API certificates for the first time")

    try:
        subprocess.check_output(["./generate-nuvlabox-api-certs.sh",
                                 "--certs-folder", utils.nuvlabox_api_certs_folder,
                                 "--server-key", utils.server_key_file,
                                 "--server-cert", utils.server_cert_file,
                                 "--client-key", utils.client_key_file,
                                 "--client-cert", utils.client_cert_file])
    except FileNotFoundError:
        logging.exception("Command to generate NuvlaBox API certs not found!")
        raise
    except (OSError, subprocess.CalledProcessError):
        logging.exception("Failed to generate NuvlaBox API certs!")
        raise


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


if __name__ == "__main__":
    """ Main """

    set_logger()
    log = logging.getLogger("api")

    # Generate NB API certificates
    generate_certificates()

    # Generate SSH key
    generate_ssh_key()

    workers = multiprocessing.cpu_count()
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

