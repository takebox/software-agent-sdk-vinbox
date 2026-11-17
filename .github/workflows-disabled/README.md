# Workflow yang tidak dipakai Vinbox

Folder ini **bukan** `.github/workflows/`, jadi GitHub Actions tidak
menjalankannya. Isinya workflow proyek asal yang membutuhkan infrastruktur yang
tidak ada di repo Vinbox ini:

| Workflow | Kenapa dipindah |
|---|---|
| `release-binaries.yml` | menerbitkan binary ke GHCR `ghcr.io/openhands/agent-server` |
| `create-release.yml`, `prepare-release.yml` | rilis upstream yang memanggil repo `Handprint/automation` |
| `version-bump-prs.yml`, `version-bump-guard.yml` | otomasi versi lintas repo upstream |
| `run-eval.yml`, `cancel-eval.yml` | eval SWE-bench upstream |
| `update-debian-snapshot.yml` | snapshot Debian untuk image upstream |
| `typescript-client-npm-publish.yml`, `typescript-client-github-packages-publish.yml` | publikasi klien TypeScript ke npm |
| `typescript-client-integration-tests.yml` | integrasi klien yang menarik image GHCR |
| `server.yml` | build image agent-server untuk GHCR |
| `integration-runner.yml` | integrasi berbasis image GHCR |
| `deploy-docs.yml` | situs dokumentasi `handprint.juglow.my.id` |
| `stale.yml` | penutup issue lama milik repo asal |
| `pr-artifacts.yml` | artefak CI upstream |
| `oh-update-documentation.yml.back` | sudah dinonaktifkan sejak awal |

Vinbox memasang paket lewat `pypi-release.yml` dan membangun image lewat
`Dockerfile` Vinbox, jadi workflow di atas tidak diperlukan.

Kalau suatu saat salah satunya dibutuhkan lagi, pindahkan kembali ke
`.github/workflows/` dan sesuaikan rahasia serta nama image-nya.
