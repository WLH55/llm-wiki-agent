FROM postgres:16

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

ARG PGVECTOR_VERSION=v0.7.4
RUN git clone --branch ${PGVECTOR_VERSION} https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && make \
    && make install \
    && rm -rf /tmp/pgvector

RUN git clone https://github.com/jaiminpan/pg_zhparser.git /tmp/pg_zhparser \
    && cd /tmp/pg_zhparser \
    && make \
    && make install \
    && rm -rf /tmp/pg_zhparser

COPY init-extensions.sql /docker-entrypoint-initdb.d/01-extensions.sql
