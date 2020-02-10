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
import threading
from flask import Flask, render_template, request
from management_api.common import utils
from multiprocessing import Process


__copyright__ = "Copyright (C) 2020 SixSq"
__email__ = "support@sixsq.com"

app = Flask(__name__)
debug_app = Flask(__name__)


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


if __name__ == "__main__":
    """ Main """

    set_logger()
    log = logging.getLogger("api")

    # Generate NB API certificates
    generate_certificates()
