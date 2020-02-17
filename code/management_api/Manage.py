#!/usr/local/bin/python3.7
# -*- coding: utf-8 -*-

""" All the management functions that can be called from the API """

import os
import time


def reboot():
    # reboot the host
    # NOTE: there's no return from this function
    time.sleep(5)
    os.system("echo b > /sysrq")


def enable_ssh():
    # TODO
    time.sleep(5)
