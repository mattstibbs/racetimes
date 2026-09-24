# Publishing the user manual on Read the Docs

The user manual lives in `manual/` as Markdown, and `mkdocs.yml` turns it into
a website with MkDocs. `.readthedocs.yaml` tells Read the Docs how to build it.
Once the project is set up, every push to `main` rebuilds the published
manual within a few minutes.

## One-time setup

1. Create an account at [readthedocs.org](https://readthedocs.org), signing
   up with GitHub so Read the Docs can see your repositories. (Read the Docs
   for Business, at readthedocs.com, is the paid version for private
   repositories; the free readthedocs.org needs the repository to be public.)
2. Choose **Add project** (or **Import a project**) and pick the `racetimes`
   repository.
3. Read the Docs finds `.readthedocs.yaml` itself. Give the project a name,
   which becomes its address, for example `racetimes` gives
   `https://racetimes.readthedocs.io`.
4. The first build starts straight away. Its log is under the project's
   **Builds** page. When it finishes, **View docs** opens the manual.
5. Check under the project's **Admin > Integrations** that a GitHub webhook
   is listed. It is what triggers a rebuild on every push; Read the Docs
   normally adds it for you.

Read the Docs changes its dashboard from time to time; if a label above does
not match, the same steps are in its "Importing your documentation" guide.

## Day to day

- **To update the manual,** change the Markdown in `manual/` in a pull
  request and merge it. Read the Docs rebuilds on the push to `main`. If the
  build fails, the previous version stays published, and the build log says
  why.
- **To preview it locally:**

  ```bash
  .venv/bin/pip install -r requirements-docs.txt
  .venv/bin/mkdocs serve        # then open http://127.0.0.1:8000
  ```

- **Adding a page:** create the Markdown file in `manual/` and add it to `nav`
  in `mkdocs.yml`. `tests/test_manual.py` fails if a page is left out of the
  contents, or if any link or image is broken.
- **Screenshots** are in `manual/images/` and are made by
  `scripts/manual_screenshots/run.sh` from sample data, so they can all be
  refreshed when the screens change. It needs Node.js with Playwright (see the
  top of the script); nothing else in the project does.

## Pull request previews

Read the Docs can also build a preview of the manual for each pull request
and link it from the pull request on GitHub. Turn it on under the project's
**Settings** ("Build pull requests for this project"). It is free on
readthedocs.org for public repositories.

## What the build runs

Read the Docs installs `requirements-docs.txt` (MkDocs only) and runs MkDocs
with `mkdocs.yml` on Python 3.11. The same build runs in CI on every pull
request (`.github/workflows/ci.yml`, "user manual builds"), in strict mode, so
a broken manual is caught before it reaches `main`.
