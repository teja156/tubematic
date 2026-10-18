# Dashboard tests

Documentation for these suites lives in the central test docs:

- **[docs/developer/test-suites/dashboard-unit.md](../../docs/developer/test-suites/dashboard-unit.md)** — vitest component,
  route-handler and helper tests (`tests/unit/`)
- **[docs/developer/test-suites/dashboard-e2e.md](../../docs/developer/test-suites/dashboard-e2e.md)** — Playwright specs, the test
  stack, and the config decisions (`tests/e2e/`)
- **[docs/developer/test-suites/README.md](../../docs/developer/test-suites/README.md)** — every suite in the repository

Quick start:

```bash
npm test                 # vitest
npm run test:e2e         # Playwright — builds the Docker test stack first (multi-GB)
```

Kept as a pointer so the docs cannot drift in two places. Update the files above, not this one.
