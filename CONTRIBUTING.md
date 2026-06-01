# Contributing to Yubi Core

Thanks for considering a contribution! Yubi Core is in its early days (pre-1.0), and bug reports, fixes, and well-scoped improvements are all welcome.

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it. To report concerns privately, contact the maintainers at `report@airoa.org`.

## Reporting issues

- **Bugs**: open a GitHub issue with a minimal reproducible example (the rosbag, task file, or config that triggers it), the Yubi Core version (git hash), and your environment (OS, ROS 2 distro, RMW implementation).
- **Security issues**: please report privately to `report@airoa.org` rather than opening a public issue.
- **Feature ideas**: open an issue to discuss before sending a large PR. Small fixes can go straight to a PR.

## Finding ways to help

Issues labeled [`good first issue`](https://github.com/airoa-org/yubi-core/labels/good%20first%20issue) and [`help wanted`](https://github.com/airoa-org/yubi-core/labels/help%20wanted) are good starting points.

Yubi Core is pre-1.0 with a deliberately narrow public surface. Before opening a PR for new functionality, please open an issue to discuss it — we may decide the feature is out of scope or needs a different shape.

## Development setup

### Clone

```bash
git clone https://github.com/airoa-org/yubi-core.git
cd yubi-core
```

### Docker (recommended)

The compose stack brings up the data collection node alongside a local MinIO
for storage:

```bash
docker compose up -d --build
docker compose exec yubi-core bash
```

See [README.md](README.md) and [docs/configuration.md](docs/configuration.md)
for environment variables and configuration.

### Local toolchain

If you prefer to develop outside Docker:

- **ROS 2**: Humble, Jazzy, or Kilted.
- **Python**: 3.10+.

The fast Python tests (node logic + the `data-backend` library) run without a
ROS 2 installation, using [uv](https://github.com/astral-sh/uv) and mocked ROS
dependencies — see below.

## Building and testing

```bash
make lint              # ruff lint + format check
make test              # ROS node tests (mocked ROS stack, no ROS install needed)
make test-gc           # data-backend unit + scenario tests (mocked S3)

# Integration tests (require Docker)
make test-integration  # storage (real MinIO) + gate (live ROS 2 stack)
```

See [docs/testing.md](docs/testing.md) for the full test architecture.

## Code style

- **Python**: `ruff` for linting and formatting. Run `make fmt` to auto-fix and
  `make lint` to check before opening a PR.

## Pull requests

- Branch from `main`.
- Run the relevant tests and lints locally before opening the PR.
- Write a clear PR description: what changed, why, and a brief test plan.
- Commits in this repository follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g. `feat:`, `fix:`, `docs:`, `chore:`, `ci:`).
- Keep changes focused — unrelated changes are easier to review as separate PRs.
- All contributions are licensed under [Apache-2.0](LICENSE).

## Use of AI

Contributors may use a variety of tools when preparing changes to Yubi Core, including AI systems (e.g. large language models or coding assistants). Contributors using such systems are expected to follow these principles:

- Regardless of how a change is produced, the individual submitting the pull request is considered the **author** of the contribution and is fully **responsible** for it.
- The pull request author **must understand the implementation end-to-end** and be able to **explain and justify the design and code** during review.
- Tools, including AI systems, **are not** considered contributors. **Responsibility and authorship remain with the human** submitting the change.
- Contributors are **encouraged to disclose** significant AI assistance in the pull request description for transparency.
- AI-generated code must be tested in your own environment — do not submit code for a robot platform or hardware path that you cannot run locally.

## Documentation

- `README.md` and `README_jp.md` are maintained as English + Japanese mirrors. If you update one, please update the other in the same change.

## Need help?

If you get stuck or want to discuss before starting, please open an issue or start a [GitHub Discussion](https://github.com/airoa-org/yubi-core/discussions).

---

Thank you for contributing to Yubi Core! 🤖
