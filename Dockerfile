
# Base image
FROM python:3.10-slim


# Optional: custom pre-build script
ARG DOCKER_PRE_BUILD=scripts/docker_pre_build.sh
COPY ${DOCKER_PRE_BUILD} /tmp/docker_pre_build.sh
RUN bash /tmp/docker_pre_build.sh


# Install system dependencies
RUN apt-get update && \
    apt-get install -y gcc g++ make cmake && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install poetry
RUN pip install poetry && poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

# Copy only necessary files for running pydexbot/main.py
COPY pydexbot/ ./pydexbot/
COPY config/ ./config/
COPY pyproject.toml ./
COPY poetry.lock ./
COPY README.md ./

# Set entrypoint
CMD ["python", "-m", "pydexbot.main"]
