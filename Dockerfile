FROM fedora:40

ARG vcs_ref=
LABEL org.label-schema.vcs-ref=$vcs_ref

RUN dnf -y update && \
    dnf -y install \
        fedora-messaging \
        git-core \
        koji \
        'libmodulemd >= 2.0' \
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

ADD pyproject.toml /opt/flatpak-status/
RUN python3 -m venv /venv --system-site-packages
env PATH="/venv/bin:$PATH" VIRTUAL_ENV=/venv

ADD flatpak-indexer/setup.py /opt/flatpak-status/flatpak-indexer/setup.py
ADD flatpak-indexer/flatpak_indexer /opt/flatpak-status/flatpak-indexer/flatpak_indexer
RUN CI=1 pip3 install -e flatpak-indexer

ADD flatpak_status /opt/flatpak-status/flatpak_status
RUN CI=1 pip3 install -e .

ADD tests /opt/flatpak-status/tests
ADD tools /opt/flatpak-status/tools
ADD web /opt/flatpak-status/web
ADD .flake8 .eslintrc.yml README.md /opt/flatpak-status/

ADD .test-data /opt/flatpak-status/.test-data
RUN tools/update-test-data.sh --no-fetch-cache
