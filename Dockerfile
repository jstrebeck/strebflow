FROM python:3.12-slim

# Install git for workspace operations
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash attractor
USER attractor
WORKDIR /home/attractor/app

# Install dependencies
COPY --chown=attractor:attractor pyproject.toml .
COPY --chown=attractor:attractor src/ src/
RUN pip install --no-cache-dir --user .

# Configure git for workspace commits
RUN git config --global user.name "attractor" && \
    git config --global user.email "attractor@local"

# Create volume mount points
RUN mkdir -p /home/attractor/workspace/runs /home/attractor/workspace/specs /home/attractor/workspace/logs

COPY --chown=attractor:attractor pipeline_config.yaml .

ENTRYPOINT ["python", "-m", "attractor"]
