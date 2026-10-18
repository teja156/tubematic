Fixed, public tokens for the isolated e2e stack (`docker-compose.test.yml`) only.
They protect nothing: that stack runs on throwaway volumes and is torn down after
every run. A real install creates random ones in `~/.tubematic-data/secrets/`.
