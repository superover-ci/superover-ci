# superover-ci

Automated on-device testing for the Super Over Android cricket game.
Free tier only: this repo is PUBLIC precisely so GitHub Actions minutes are
free. It contains ONLY the test rig - no game source code, no APK, no signing
material. The game build under test is a debug-signed CI build fetched from
private links stored in repository secrets (SUPEROVER_APK_PART_IDS,
SUPEROVER_APK_SHA256).

What runs:
- Hourly (autotest-hourly.yml): one emulator, rotating Android 11/12/12L/13/14
  (API 30-34), rotating device profile (pixel_6 / Nexus 6), rotating seeds,
  6 seeded auto-play sessions. Results land as artifacts named hourly-apiXX-runN.
- Weekly + per-build (autotest-full.yml): full matrix, one emulator per API
  level. Every new build is dispatched twice with different seeds/profiles
  (2 full runs per build). Results land as artifacts named full-apiXX-runN.

The driver (driver.py) needs no game changes: it reads the screen via the
built-in uiautomator dump, injects taps/swipes (double-tap = activate, matching
the game's TalkBack-off gesture semantics), runs feature tours (quick T20, ODI
setup, gesture guide, What's New, settings), records CRASH / STALL /
SILENT_SPEECH events, and saves labelled screenshots of every feature screen
it reaches (menu, setup, Playing 11, toss, live match, live panel, drinks,
guide, What's New, results, settings) for visual review.

Honest scope: randomized soak/smoke coverage + feature-screen presence +
visual captures. It does not verify scoring rules; that stays with the game's
own Node test suites.
