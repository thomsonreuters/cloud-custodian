#!/bin/bash

virtualenv testing
source testing/bin/activate
pip install tox
tox -e py27
