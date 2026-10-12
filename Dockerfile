# Built and pushed by brick9000/build-image in brick-cicd-config:
#   build-image https://github.com/operations-ivy/overwatch main whitepatrick/overwatch:<version>
#
# One image, two roles (k8s_config/): `scan` and `web`. The base image is
# pinned by digest and dependencies come from poetry.lock. Bump the base
# deliberately, with the digest from:
#   docker buildx imagetools inspect python:3.11-slim-bookworm
ARG PYTHON=python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b

# Poetry installs the locked dependencies into /venv; only /venv is kept.
FROM ${PYTHON} AS deps
ARG POETRY_VERSION=2.1.2
ENV PIP_DEFAULT_TIMEOUT=120 POETRY_NO_INTERACTION=1 VIRTUAL_ENV=/venv PATH=/venv/bin:$PATH
# One package at a time: the parallel installer races on the umask (wigle-sync).
ENV POETRY_INSTALLER_PARALLEL=false
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"
WORKDIR /code
COPY pyproject.toml poetry.lock /code/
RUN python -m venv --without-pip /venv && poetry install --no-root --only main

FROM ${PYTHON}
COPY --from=deps /venv /venv
# Read-only root filesystem in the cluster, so no .pyc files.
ENV VIRTUAL_ENV=/venv PATH=/venv/bin:$PATH PYTHONPATH=/code PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /code
COPY overwatch/ /code/overwatch/

# Not root: BlueZ's D-Bus policy lets any user scan. It must be a uid the
# host knows, though: the system bus drops a connection from one with no
# passwd entry (65532 got "connection reset"), so this is nobody:nogroup.
USER 65534:65534
EXPOSE 8080
ENTRYPOINT ["python", "-m", "overwatch"]
