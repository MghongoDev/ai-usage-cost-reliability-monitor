# GitHub Actions cron drives collection, Render serves Grafana

Status: accepted

The guide assumed one always-on worker container on a small VM. Render's free tier cannot run always-on compute: free web services sleep after 15 idle minutes, background workers and private services have no free tier, and free Postgres expires 30 days after creation. So the system splits instead. A scheduled GitHub Actions workflow boots the simulator, runs collectors, probes, and rules, and writes to Render's free Postgres. A free web service serves Grafana against that database, and a nightly pg_dump runs as a CI artifact so the 30-day expiry does not lose history. The cost of this shape is a coarser deployed cadence, capped by free Actions minutes on a private repo, and a dashboard that takes a minute to wake after 15 idle minutes.
