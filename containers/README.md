# Runner images

`pyfixagent-runner:0.7.1` is the reviewed Linux/amd64 scientific profile used by the bundled fixtures. Its base image, complete Python resolution, and wheel artifacts are pinned. Runtime installation is disabled.

Build it with provenance metadata:

    docker build --pull=false --provenance=mode=max -f containers/Dockerfile -t pyfixagent-runner:0.7.1 .

Docker Desktop can generate and inspect the local SBOM after the build:

    docker scout sbom pyfixagent-runner:0.7.1 --format list
    pyfixagent-verify-container --image pyfixagent-runner:0.7.1

Projects needing different dependencies should create a separately reviewed derived image. Install dependencies during image construction as root, require hashes, and restore the non-root runtime user:

    FROM pyfixagent-runner:0.7.1
    USER 0:0
    COPY requirements.project.lock /tmp/requirements.project.lock
    RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.project.lock \
        && rm /tmp/requirements.project.lock
    USER 65534:65534

Select it with `--container-image my-project-runner:reviewed`. Do not mount credentials or the Docker socket into repair containers.
