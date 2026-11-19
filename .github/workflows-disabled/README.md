# Workflow yang tidak dipakai Vinbox

Folder ini **bukan** `.github/workflows/`, jadi GitHub Actions tidak
menjalankannya. Isinya workflow proyek asal yang membutuhkan infrastruktur yang
tidak ada di repo Vinbox ini:

| Workflow | Kenapa dipindah |
|---|---|
| `release-binaries.yml` | menerbitkan binary ke GHCR `ghcr.io/handprint/agent-server` |
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

Penjaga (test) untuk workflow yang dinonaktifkan tetap ada di `tests/cross/`,
tetapi dilewati dengan alasan yang jelas selama file workflow-nya tidak ada —
lihat `requires_server_workflow` di `test_agent_server_build_metadata.py`,
`pytestmark` di `test_server_workflow_binary_smoke.py`, dan
`requires_snapshot_workflow` di `test_update_debian_snapshot.py`. Jadi aturan
di dalamnya tidak hilang: begitu workflow dipulihkan, test-nya otomatis jalan
lagi.

Kalau suatu saat salah satunya dibutuhkan lagi, pindahkan kembali ke
`.github/workflows/` dan sesuaikan rahasia serta nama image-nya.
