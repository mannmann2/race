# Race Atlas

Browse trail races and marathons on an interactive globe. Combines UTMB, ITRA and World’s Marathons, with filters for dates, distance, location and ratings.

**[race.slopmaxx.ing](https://race.slopmaxx.ing)**

## Run locally

Requires Node.js 22+ and Python 3.10+. No npm dependencies to install.

```sh
# A fresh checkout needs sample data:
node scripts/seed-demo.mjs
npm run compose
npm run dev
```

Open **http://localhost:4173**. The sample contains two synthetic races; production snapshots are kept out of Git. Skip seeding if you already have data.

## Deploy

Production runs through `race-atlas.service`, behind a reverse proxy pointing to **127.0.0.1:4173**.

On this server, use the app’s Node runtime:

```sh
export PATH=/opt/race/node/bin:$PATH
npm run test:all
npm run build -- --stage
```

Preview the staged release before activating it:

```sh
SERVE_DIR=/root/race/.releases/<release> PORT=4174 npm run dev
# In another terminal:
TEST_URL=http://127.0.0.1:4174 /opt/race/venv/bin/python3 tests/launch-browser.py
```

Then deploy:

```sh
npm run deploy
sudo systemctl restart race-atlas.service
```

`npm run rollback` restores the previous release. `npm run prune` removes older releases.

For initial server setup, `sudo bash deploy/install.sh` installs the runtimes, service users and units for `/root/race`. Install the browser’s Linux dependencies and `xvfb`/`xauth` first. After activating a release, enable the services:

```sh
sudo systemctl enable --now race-atlas.service race-refresh.timer race-health.timer
```

## Data refresh and monitoring

The refresh timer runs daily at **03:30 UTC**, with up to 10 minutes of jitter. UTMB and ITRA course details refresh daily; ITRA’s bulk calendar and World’s Marathons refresh weekly. Date windows advance automatically.

```sh
sudo systemctl start race-refresh.service       # refresh and publish now
systemctl list-timers 'race-*'
journalctl -u race-refresh.service -n 60
curl http://127.0.0.1:4173/healthz
```

Failed imports retain the last verified data. Successful runs publish without restarting the website and save checksummed backups in `.cache/backups/`, keeping the latest 14. Health checks run every 15 minutes. Off-server backups and external alerts are not configured; optional settings are in [.env.example](.env.example).

## About the data

Duplicates merge only when event, date and course evidence agree. Ambiguous matches stay separate, and merged races retain their source links and ratings. Reviewed exceptions live in `scripts/source-overrides.json`.

Locations may represent a town or event rather than the exact start. Photos and ratings appear when supplied. Counts and source freshness are shown in the app.

See [DATA_MODEL.md](DATA_MODEL.md) for the schema and matching rules, and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for credits. Independent project; not affiliated with the data providers. Confirm race details with organisers.
