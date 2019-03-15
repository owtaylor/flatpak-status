FROM fedora:29

ARG vcs_ref=
LABEL org.label-schema.vcs-ref=$vcs_ref

RUN dnf -y update && \
    dnf -y install \
        git-core \
        koji \
        'libmodulemd >= 2.0' \
        pipenv \
        python3-fedmsg \
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
RUN PIPENV_VENV_IN_PROJECT=1 pipenv --three --site-packages && \
    pipenv install --dev

ADD flatpak_status /opt/flatpak-status/flatpak_status
ADD setup.py /opt/flatpak-status/
RUN pipenv run pip3 install -e .

ADD tests /opt/flatpak-status/tests
ADD utils /opt/flatpak-status/utils
ADD web /opt/flatpak-status/web
ADD .flake8 .eslintrc.yml README.md /opt/flatpak-status/

CMD ["pipenv", "shell"]
