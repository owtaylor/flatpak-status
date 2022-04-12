FROM fedora:35

ARG vcs_ref=
LABEL org.label-schema.vcs-ref=$vcs_ref

RUN dnf -y update && \
    dnf -y install \
        fedora-messaging \
        git-core \
        koji \
        'libmodulemd >= 2.0' \
        pipenv \
        python3-bodhi-messages \
        python3-fedora-messaging \
        python3-gobject-base \
        python3-koji \
        python3-pip \
        rsync \
        nodejs \
        which

RUN mkdir /opt/flatpak-status
WORKDIR /opt/flatpak-status

ADD package.json /opt/flatpak-status/
RUN npm install

ADD Pipfile /opt/flatpak-status/
RUN PIPENV_VENV_IN_PROJECT=1 CI=1 pipenv --three --site-packages && \
    CI=1 pipenv install --dev

ADD flatpak-indexer/setup.py /opt/flatpak-status/flatpak-indexer/setup.py
ADD flatpak-indexer/flatpak_indexer /opt/flatpak-status/flatpak-indexer/flatpak_indexer
RUN CI=1 pipenv run pip3 install -e flatpak-indexer

ADD flatpak_status /opt/flatpak-status/flatpak_status
ADD setup.py /opt/flatpak-status/
RUN CI=1 pipenv run pip3 install -e .

ADD tests /opt/flatpak-status/tests
ADD tools /opt/flatpak-status/tools
ADD web /opt/flatpak-status/web
ADD .flake8 .eslintrc.yml README.md /opt/flatpak-status/

ADD .test-data /opt/flatpak-status/.test-data
RUN CI=1 pipenv run tools/update-test-data.sh --no-fetch-cache

ENV PIPENV_SHELL=/bin/bash

CMD ["pipenv", "shell"]
