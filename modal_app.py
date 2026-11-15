"""Deploy the owner view (review/web) to Modal as a static site.

    pip install modal
    modal setup                 # one-time login
    modal serve modal_app.py    # temporary URL, reloads on edits
    modal deploy modal_app.py   # permanent URL

Run `npm run render` first if the evidence changed, so web/data.js is current.
The page is static: the Rules page's Save button (POST /api/rules) only works
with the local dev server.
"""
import modal

image = (
    modal.Image.debian_slim()
    .pip_install("fastapi[standard]")
    .add_local_dir("review/web", remote_path="/web")
)

app = modal.App("earned-trust", image=image)


@app.function()
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def web():
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    api = FastAPI()
    api.mount("/", StaticFiles(directory="/web", html=True), name="web")
    return api
