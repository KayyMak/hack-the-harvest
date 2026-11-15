# Contributing

Read [START_HERE.md](START_HERE.md) for setup and [ENGINEERING.md](ENGINEERING.md)
for repository rules before implementing a task.

Create a branch from current `main`, agree on the files/components being worked
on, and keep each PR focused. The frontend, backend, and analysis have separate
folders so teammates can work independently. Coordinate changes to API response
models and the matching frontend types before implementing both sides.

Use the requested conventional commit format:

```text
feat(frontend): add field-year filtering
fix(api): handle missing baseline artifacts
test(baseline): check repeated-field validation
docs(setup): clarify Python environment commands
```

Common types are `feat`, `fix`, `docs`, `test`, `refactor`, `build`, `ci`, and
`chore`. The scope is optional.

Before opening a PR, run the checks for the components changed. Include what
changed, how it was verified, and any material limitations. Include before/after
screenshots for meaningful UI changes. CI checks the frontend build and backend
API contracts. For analysis changes, include relevant validation and resulting
metrics; do not tune against held-out test results and report them as untouched.

Preserve the source data and notebooks. Generated numerical outputs belong in
`baseline/outputs/`, with provenance in `baseline/cache/`. Never commit local
environments, credentials, dependencies, or built frontend bundles.
