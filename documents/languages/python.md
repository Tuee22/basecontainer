---
name: languages-python
description: Python conventions inside the basecontainer base image.
type: guide
---

# Python

The base image carries the Ubuntu 24.04 default Python 3 with Poetry as the
**only** global Python package. Everything else lives inside the project's
own dependencies.

## Caches

The image sets the standard cache directories under `/opt/cache`:

* `PIP_CACHE_DIR=/opt/cache/python/pip`
* `POETRY_CACHE_DIR=/opt/cache/python/pypoetry`
* `PYTHONPYCACHEPREFIX=/opt/build/python/pycache`
* `POETRY_VIRTUALENVS_CREATE=false`
* `POETRY_VIRTUALENVS_IN_PROJECT=false`

Container-installed Poetry must not create per-project venvs inside the
container: that is the host-side concern.

## Host isolation

Downstream projects that maintain their own host-level `.venv` (e.g. ML
inference Python adapters) must **never** add `hostbootstrap` to that venv.
By bootstrap time, hostbootstrap's job is done; it has no place inside a
project's runtime environment. See §10 of the plan.

## hostbootstrap itself

The hostbootstrap repo uses Poetry with an **in-project** `.venv`
(`poetry.toml` sets `virtualenvs.in-project = true`) — *for repo
development only*. Downstream installs go into host Python via `pip install
git+…`.
