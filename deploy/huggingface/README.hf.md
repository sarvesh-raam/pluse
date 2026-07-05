---
title: Pulse
emoji: ⚡
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Pulse — Distributed Job Scheduler

A production-inspired distributed background-job platform: atomic job
claiming across any number of workers, configurable retries with backoff
and jitter, a dead letter queue with one-click replay, workflow
dependencies, cron/recurring jobs, live dashboard updates, and
AI-generated failure summaries.

**Demo login:** `demo@pulse.dev` / `demo1234`

This Space runs the frontend, API, scheduler, and worker together in a
single container (via supervisord) against an external Neon Postgres
database — see the main repo's `docker-compose.yml` for the normal
multi-container local dev setup.

Source: https://github.com/sarvesh-raam/pulse-jobscheduler
