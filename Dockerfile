# Container for https://llms.2plot.dev — the documentation site for
# dash-improve-my-llms, which is also this package's reference deployment.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Requirements first so the dependency layer survives edits to app code.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# The package is installed from the committed release sdist rather than the
# working tree or PyPI: the other network apps vendor this exact artifact, so
# the reference host must run the same bytes it asks everyone else to run.
# A code change reaches production only after `python -m build` refreshes
# dist/ and the sdist is committed — that is the release discipline.
COPY dist/dash_improve_my_llms-*.tar.gz ./dist/
RUN pip install --no-cache-dir --no-deps ./dist/dash_improve_my_llms-*.tar.gz

COPY app.py ./
COPY pages ./pages
COPY docs ./docs

# Render injects PORT; 8959 matches the local default in app.py.
ENV PORT=8959
EXPOSE 8959

# One worker would serialise a crawler sweep behind a slow page render, so run
# a small pool. Threads (not extra workers) carry the concurrency, because the
# package's in-process state — page metadata, the bulletin cache — is
# per-process and a large worker count just multiplies cold caches.
CMD ["sh", "-c", "gunicorn app:server \
    --bind 0.0.0.0:${PORT:-8959} \
    --workers ${WEB_CONCURRENCY:-2} \
    --threads 4 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -"]
