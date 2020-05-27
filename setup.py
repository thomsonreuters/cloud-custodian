import os
from io import open
from setuptools import setup, find_packages


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname), encoding='utf-8').read()


setup(
    name="c7n",
    version='0.8.33.1',
    description="Cloud Custodian - Policy Rules Engine",
    long_description=read('README.rst'),
    classifiers=[
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Distributed Computing"
    ],
    url="https://github.com/capitalone/cloud-custodian",
    license="Apache-2.0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'custodian = c7n.cli:main']},
    install_requires=[
        "boto3==1.9.249",
        "botocore==1.12.249",
        "python-dateutil==2.6",
        "pyyaml==3.12",
        "jsonschema==2.5.1",
        "jsonpatch==1.2.1",
        "argcomplete==1.8.2",
        "tabulate==0.8.2",
        "futures==3.1.1"
    ],
)
