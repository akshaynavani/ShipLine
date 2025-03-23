# ShipLine — Implementation Plan

**ShipLine** is a CI/CD deployment pipeline written in Python and Shell. A single command
takes a service from source to a running Kubernetes deployment on AWS EKS:

```
lint/static analysis -> pytest -> docker build -> push to ECR -> kubectl deploy to EKS -> verify rollout
```

Every release is tagged (git SHA + timestamp) and recorded, so any previous release can be
redeployed with `shipline rollback`.

**Tech:** Python 3.11, Bash, Docker, AWS ECR, AWS EKS, Kubernetes (kubectl), pytest.

## Key design decisions

- **Python orchestrator, thin Shell wrappers.** Pipeline logic (stage ordering, tagging,
  templating, release history, rollback) lives in a testable Python package. Shell scripts
  (`scripts/*.sh`) are convenience entry points for CI runners and local bootstrap.
- **External tools via a single `CommandRunner`.** All calls to `docker`, `aws`, `kubectl`,
  `pytest`, `ruff`, `mypy` go through one runner with a dry-run mode, so the whole pipeline
  can be unit-tested with a fake runner and previewed without touching AWS.
- **Config file `shipline.yaml`** per service: app name, AWS region/account, ECR repo,
  EKS cluster, namespace, manifest directory, check commands. Environment variables
  override secrets-adjacent values (account id, region); no credentials are ever stored.
- **Immutable image tags.** `<short-sha>-<UTC timestamp>`; `latest` is never deployed.
- **Release history in a Kubernetes ConfigMap** (`shipline-releases`) inside the target
  namespace, with a local JSON fallback. Keeping history in the cluster means any CI runner
  can roll back without shared local state.
- **Manifests are templated** with a minimal `${VAR}` substitution (string.Template) rather
  than Helm, keeping the dependency surface small.

## Phases

### Phase 1 — Package skeleton, config and command runner
Deliverables: installable package, CLI with subcommands stubbed, config loading/validation,
command runner with dry-run, structured logging.
Files: `pyproject.toml`, `shipline/__init__.py`, `shipline/cli.py`, `shipline/config.py`,
`shipline/runner.py`, `shipline/logging_utils.py`, `shipline/errors.py`, `shipline.example.yaml`.

### Phase 2 — Quality gate stage (static analysis + pytest) and sample service
Deliverables: pipeline stage abstraction, `checks` stage running ruff, mypy and pytest with
JUnit output, a small sample Flask service with its own tests to deploy.
Files: `shipline/stages/base.py`, `shipline/stages/checks.py`, `shipline/pipeline.py`,
`examples/hello-service/**`.

### Phase 3 — Docker build and ECR push
Deliverables: image tagging scheme, docker build with build args + labels, ECR repository
ensure/create, ECR login via `aws ecr get-login-password`, push.
Files: `shipline/tagging.py`, `shipline/stages/build.py`, `shipline/stages/publish.py`,
`shipline/aws.py`.

### Phase 4 — EKS deploy, release history and rollback
Deliverables: kubeconfig update for EKS, manifest rendering, `kubectl apply`, rollout status
wait with automatic rollback on failure, release recording, `shipline releases` and
`shipline rollback [--to TAG]`.
Files: `shipline/kube.py`, `shipline/manifests.py`, `shipline/releases.py`,
`shipline/stages/deploy.py`, `shipline/rollback.py`, `examples/hello-service/k8s/*.yaml`.

### Phase 5 — Shell entry points, CI workflow and pipeline tests
Deliverables: `scripts/ship.sh`, `scripts/rollback.sh`, `scripts/bootstrap.sh`, GitHub Actions
workflow using OIDC to assume an AWS role, pytest suite for ShipLine itself using a fake runner.
Files: `scripts/*.sh`, `.github/workflows/deploy.yml`, `tests/**`, `.env.example`.

After the phases: `.gitignore` and `README.md` with an architecture diagram.
