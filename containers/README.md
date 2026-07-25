# Runner images

`pyfixagent-runner:0.7.2` is the reviewed Linux/amd64 scientific profile used by the bundled fixtures. Its base image, Python resolution, and wheel artifacts are pinned; runtime dependency installation is disabled.

Build it with provenance metadata:

    docker build --pull=false --provenance=mode=max -f containers/Dockerfile -t pyfixagent-runner:0.7.2 .

If Docker Scout is installed and can inspect local images, inspect the image and apply the repository's allowlist check:

    docker scout sbom pyfixagent-runner:0.7.2 --format list
    pyfixagent-verify-container --image pyfixagent-runner:0.7.2

`profiles.json` defines three finite profiles:

- `minimal`: pytest and its Linux runtime dependencies.
- `scientific`: pytest, NumPy, scikit-learn, and matplotlib; this remains the default.
- `web`: pytest and Flask.

Build a non-default profile by selecting its reviewed lock explicitly:

    docker build --build-arg RUNNER_PROFILE=minimal --build-arg REQUIREMENTS_LOCK=containers/profiles/minimal.lock -f containers/Dockerfile -t pyfixagent-runner:0.7.2-minimal .
    docker build --build-arg RUNNER_PROFILE=web --build-arg REQUIREMENTS_LOCK=containers/profiles/web.lock -f containers/Dockerfile -t pyfixagent-runner:0.7.2-web .

Every non-comment lock line contains an exact wheel hash. The image label `io.pyfixagent.runner.profile` records the selected profile. The release workflow builds and smoke-tests each profile before publication.

Projects needing different dependencies should create a separately reviewed derived image. Install dependencies during image construction as root, require hashes, and restore the non-root runtime user:

    FROM pyfixagent-runner:0.7.2
    USER 0:0
    COPY requirements.project.lock /tmp/requirements.project.lock
    RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.project.lock \
        && rm /tmp/requirements.project.lock
    USER 65534:65534

Select it with `--container-image my-project-runner:reviewed`. Do not mount credentials or the Docker socket into repair containers.

On a pushed version tag, `.github/workflows/release-runner.yml` publishes versioned profile images to GHCR after its profile checks succeed, with BuildKit SBOM/provenance attestations and a GitHub OIDC build-provenance signature. Verify a published subject with GitHub CLI:

    gh attestation verify oci://ghcr.io/instruzhao/pyfixagent-runner:0.7.2 --repo instruzhao/pyfix-agent

The publication workflow is inactive for ordinary local commits and branch pushes.
