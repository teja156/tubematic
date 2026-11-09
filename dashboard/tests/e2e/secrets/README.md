Fixed, public tokens for the isolated e2e stack (`docker-compose.test.yml`) only.
They protect nothing: that stack runs on throwaway volumes and is torn down after
every run. A real install creates random ones in `~/.tubematic-data/secrets/`.

The render gateway's TLS pair (`render_tls_key`, `render_tls_cert`) is not
committed: a private key, even a test one, does not belong in the repository.
`../global-setup.ts` creates it here with `openssl` when it is missing, and
`.gitignore` keeps it out of git.
