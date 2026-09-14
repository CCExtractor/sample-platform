# Web console

The platform's browser client. A Vite + React single-page app that talks to
the `mod_api` blueprint at `/api/v1` and nothing else — no server of its own,
no session cookie, no template rendering.

## Working on it

```sh
npm install
npm run dev          # http://localhost:5173, API proxied to the backend
```

`npm run lint` and `npx tsc -b` are what CI checks.

## Building for the platform

```sh
npm run build:app    # static dist/, based at /app/
```

`--base=/app/` matters: the console is served from a path on the platform's own
domain, not from a root. Nginx maps `/app/` at that build output — see the
`location ^~ /app/` block in `install/nginx.conf`.

Being on the same origin as the API is deliberate. It means no CORS, no second
certificate, and no third party in the path when someone signs in.

## Deployment

The console is built by `sp-deployment-pipeline.yml` on the runner and only
the build output is copied to the VM, so the server needs no Node toolchain.
It lands in `web/app/` — the directory name matches the `/app/` URL so nginx
can serve it with a plain `root`. Nothing here is served by Flask.

Set `CONSOLE_URL` in `config.py` so password-reset emails link to the console
rather than the classic pages. `install.sh` writes it for new installs.

---

Built by Pulkit Chauhan ([@pulk17](https://github.com/pulk17)) during Google
Summer of Code 2026.
