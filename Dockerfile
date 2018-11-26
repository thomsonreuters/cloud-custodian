FROM alpine:3.8
RUN apk add py-pip
ADD . /src
WORKDIR /src
RUN pip install -r requirements.txt
RUN python setup.py develop

VOLUME ["/var/log/cloud-custodian", "/etc/cloud-custodian"]
