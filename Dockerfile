ARG MINIO_CLIENT_IMAGE_TAG=RELEASE.2022-03-17T20-25-06Z
ARG MINICONDA_IMAGE_TAG=4.10.3-alpine

FROM minio/mc:$MINIO_CLIENT_IMAGE_TAG AS mc

FROM continuumio/miniconda3:$MINICONDA_IMAGE_TAG

COPY --from=mc /usr/bin/mc /usr/bin/mc

# add bash, because it's not available by default on alpine
# and ffmpeg because we need it for streaming
# and ca-certificates for mc
# and git to get pystreams
RUN apk add --no-cache bash ffmpeg ca-certificates git

# install poetry
COPY ./requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/requirements.txt

# create new environment
# see: https://jcristharif.com/conda-docker-tips.html
# warning: for some reason conda can hang on "Executing transaction" for a couple of minutes
COPY environment.yml /tmp/environment.yml
RUN conda env create -f /tmp/environment.yml && \
    conda clean -afy && \
    find /opt/conda/ -follow -type f -name '*.a' -delete && \
    find /opt/conda/ -follow -type f -name '*.pyc' -delete && \
    find /opt/conda/ -follow -type f -name '*.js.map' -delete

# "activate" environment for all commands (note: ENTRYPOINT is separate from SHELL)
SHELL ["conda", "run", "--no-capture-output", "-n", "emishows", "/bin/bash", "-c"]

# add poetry files
COPY ./emishows/pyproject.toml ./emishows/poetry.lock /tmp/emishows/
WORKDIR /tmp/emishows

# install dependencies only (notice that no source code is present yet) and delete cache
RUN poetry install  --no-root && \
    rm -rf ~/.cache/pypoetry

# add source and necessary files
COPY ./emishows/src/ /tmp/emishows/src/
COPY ./emishows/LICENSE ./emishows/README.md /tmp/emishows/

# build wheel by poetry and install by pip (to force non-editable mode)
RUN poetry build -f wheel && \
    python -m pip install --no-deps --no-index --no-cache-dir --find-links=dist emishows

ENV EMISHOWS_DB_HOST=localhost \
    EMISHOWS_DB_PORT=34000 \
    EMISHOWS_EMITIMES_HOST=localhost \
    EMISHOWS_EMITIMES_PORT=36000 \
    EMISHOWS_EMITIMES_USER=user \
    EMISHOWS_EMITIMES_PASSWORD=password \
    EMISHOWS_EMITIMES_CALENDAR=emitimes

EXPOSE 35000

ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "emishows", "emishows", "--port", "35000"]
