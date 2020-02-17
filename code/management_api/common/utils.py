#!/usr/local/bin/python3.7
# -*- coding: utf-8 -*-

""" Common set of managament methods to be used by
 the different management api classes """

import docker
import requests
import logging

data_volume = "/srv/nuvlabox/shared"
log_filename = "management-api.log"

server_cert_file = "nuvlabox-api-server-cert.pem"
server_key_file = "nuvlabox-api-server-key.pem"
client_cert_file = "nuvlabox-api-client-cert.pem"
client_key_file = "nuvlabox-api-client-key.pem"
ca_file = "ca.pem"

nuvlabox_api_certs_folder = "{}/nuvlabox-api".format(data_volume)

ssh_key_file = "{}/nuvlabox-ssh-key".format(data_volume)

return_404 = {"status": 404,
              "message": "undefined"}

return_405 = {"status": 405,
              "message": "undefined"}

return_200 = {"status": 200,
              "message": "undefined"}

return_201 = {"status": 201,
              "message": "undefined"}
