flatpak-status
==============

This is a small web application for displaying the status of Flatpaks in Fedora.
An update process retrieves information from koji.fedoraproject.org,
bodhi.fedoraproject.org and
src.fedoraproject.org with caching,
computes a status for each active Flatpak build,
and writes a JSON file containing the status.

Then a static vue.js application creates the display from the status.

The update process
==================

`
$ flatpak-status --cachedir=<cachedir> update -o <some_directory>/status.json
`

Because updating all the repositories from src.fedoraproject.org takes a very long time,
git mirroring can be done as a background process.

`
$ flatpak-status --cachedir=<cachedir> git-mirror &
[...]
$ flatpak-status --cachedir=<cachedir> --no-update-existing update
[...]
$ flatpak-status --cachedir=<cachedir> --no-update-existing update
`

Configuring the web
===================

You should configure your web server so that
status.json and the files under web/ -
`index.html`,
`status.css`,
and `status.js` are all available with the same path.

Development
===========

Setup
-----

``` sh
dnf install pipenv python3-fedmsg python3-koji python3-pip
pipenv --three --site-packages
pipenv install --dev -e .
pipenv run pip install -e .
npm install
```

You can then enter an interactive session with `pipenv shell`

Coding style
------------
* All Python code is expected to be clean according to flake8
(as configured by `.flake8`),
* The Javascript code is expected to be clean according to eslint
(As configured by `.eslintrc`).
* All tests should pass.

`utils/test.sh` runs the unit tests, flake8, and eslint.
`utils-test-podman.sh` runs test.sh in container.

Test Data
---------
The tests use a subset of Fedora package data.

`utils/create-test-data.py` can either download the test data from scratch,
or more usually, update it based on an existing download. This script
is not used directly, instead you run:

`utils/update-test-data.sh` - this updates the test data based either
on the test-data/ directory, if it exists, or from the test-data-cache
git branch.

Caching a recen version of the test-data in a git branch allows for efficient
continous integration tests.

License
=======
flatpak-status is copyright Red Hat, 2019 and available under the terms of the MIT license.




