# Staging Lifecycle Checklist — Employee App Auto-Upgrade

Use this checklist on staging only. Do **not** deploy to production without explicit authorization.

## Prerequisites

- [ ] Backend migrated: `alembic upgrade head` (includes `0011_application_releases`)
- [ ] `RELEASE_CI_TOKEN` and `RELEASE_STORAGE_DIR` set in staging `.env`
- [ ] GitHub secrets `RELEASE_API_BASE` and `RELEASE_CI_TOKEN` configured for desktop release workflow
- [ ] Admin can open **System → App Releases** on the web portal

## Lifecycle

1. [ ] Bump `desktop/package.json` version (e.g. `0.1.1`) and push tag `v0.1.1` (or run workflow_dispatch)
2. [ ] GitHub Actions builds Electron NSIS (`WorkPulse-Employee-Setup-*.exe`)
3. [ ] CI registers release via `POST /api/v1/releases/ci-register` with status **uploaded**
4. [ ] Website **App Releases** shows “New application version uploaded”
5. [ ] Admin reviews notes / size / SHA, then **Approve** and **Publish**
6. [ ] Packaged WorkPulse Employee on a test PC detects update (banner / check)
7. [ ] Update downloads; integrity hash matches published package
8. [ ] App restarts into new version
9. [ ] Server records `employee_update_history` success and `devices.agent_version` updates
10. [ ] Simulate failed download (stop API mid-download) — app still usable; failure reported
11. [ ] Pause published release — feed returns 404; devices stop offering that update
12. [ ] Roll forward with a higher patch for rollback scenarios (electron-updater rejects downgrades)
13. [ ] Second employee device updates independently; compliance table shows both

## Out of scope for Phase 1

- macOS builds
- Authenticode signing (optional when certs exist)
- Automatic production publish from git push
- Production deployment
