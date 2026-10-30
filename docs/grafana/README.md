# Grafana provisioning: dashboards and data sources.

Dashboards are provisioned from JSON files in git so dashboard changes are
reviewable in pull requests. The Grafana instance serves anonymous read-only
access, shown as a free-tier web service.

Structure:
- dashboards/: dashboard JSON files, one per dashboard
- datasources.yml: data source configuration (Postgres + simulator)

This directory is mounted into the Grafana container at /etc/grafana/provisioning/.

Dashboards:
- overview: total usage, cost, and provider availability across both vendors
- cost: per-scope and per-key monthly cost, reconciliation
- usage: per-key usage over time
- availability: probe-based availability and SLO burn

All dashboards are provisioned from this directory, so dashboard changes are
explicitly reviewed and committed.
