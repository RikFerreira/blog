# backend

Reserved for the application backend — code, databases and related assets.

Nothing lives here yet. The site currently served at rikalves.com is fully
static: `frontend/build.py` renders `frontend/content/` into `frontend/site/`,
and nginx serves the result. When a feature needs server state, it goes here.
