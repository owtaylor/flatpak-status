flatpak-status
==============

This is a small web application for displaying the status of Flatpaks in Fedora.
An update process retrieves information from koji.fedoraproject.org,
bodhi.fedoraproject.org and
src.fedoraproject.org with caching,
computes a status for each active Flatpak build,
and writes a JSON file containing the status.

Then a static vue.js application creates the display from the status.

Running updates
===============

``` sh
$ flatpak-status -c <configfile> update
```

Runs a one-off update. Options are:

**--mirror-existing/--no-mirror-existing**
Enable (the default) or disable updating src.fedoraproject.org repositories that have already been mirrored.
This can be used to speed things up during testing.


``` sh
$ flatpak-status -c <configfile> daemon
```

This runs a continuous update process. The fedmsg message bus is monitored for commits to
src.fedoraproject.org, which  accelerates the update process, since it isn't necessary
to loop through and check for updates to the repositories one-by-one.

**-o/--output**
Output filename


Configuring the web
===================

You should configure your web server so that the generated
`status`.json and the files under web/ -
`index.html`,
`status.css`,
and `status.js` are all available with the same path.

Development
===========

Setup
-----

``` sh
dnf install libmodulemd npm pipenv python3-fedmsg python3-gobject-base python3-koji python3-pip
pipenv --three --site-packages
pipenv install --dev -e .
pipenv run pip install -e .
npm install
```

You can then enter an interactive session with `pipenv shell`

Trying it locally
----------------

Run a redis service for caching in one terminal tab:

``` sh
./tools/build-redis.sh
./tools/run-redis.sh
```

Run flatpak-status in another terminal tab to create `status.json`:

``` sh
flatpak-status -v -c config-example.yaml update
```

(Pass `--no-mirror-existing`, if running it repeatedly, to skip updating all the git repositories.)

Then run a web server in a third terminal tab:

``` sh
./tools/build-frontend.sh
./tools/run-frontend.sh
```

And go to `localhost:8080` in your web browser. The `web/` and `generated/` directories are mounted
in the web server, so you can simply reload when rebuilding `status.json` or editing javascript/CSS
files.

Coding style
------------
* All Python code is expected to be clean according to flake8
(as configured by `.flake8`),
* The Javascript code is expected to be clean according to eslint
(As configured by `.eslintrc`).
* All tests should pass.

`tools/test.sh` runs the unit tests, flake8, and eslint.
`tools-test-podman.sh` runs test.sh in container.

Test Data
---------
The tests use a subset of Fedora package data.

`tools/create-test-data.py` can either download the test data from scratch,
or more usually, update it based on an existing download. This script
is not used directly, instead you run:

`tools/update-test-data.sh` - this updates the test data based either
on the test-data/ directory, if it exists, or from the test-data-cache
git branch.

Caching a recent version of the test-data in a git branch allows for efficient
continous integration tests.

License
=======
flatpak-status is copyright Red Hat, 2019 and available under the terms of the MIT license.




