# Bullet Steps Service

**Owner:** Sam
**RTO:** 40 min
**RPO:** 10 min

## Dependencies

- bullet-postgres (database, critical)

## Recovery Steps

- Restart the bullet service. Owner: Sam. 15 min.
  - Verify: `curl -f localhost/health`
- Reconnect the database. Owner: Sam. 25 min.
  ```
  psql -h bullet-postgres -c "select 1;"
  ```
