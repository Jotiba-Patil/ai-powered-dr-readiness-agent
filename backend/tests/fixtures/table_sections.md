# Table Sections Service

**Owner:** Robin
**RTO:** 90 min
**RPO:** 20 min

## Dependencies

| Name | Type | Critical |
|------|------|----------|
| table-postgres | database | yes |
| table-queue | messaging | no |

## Recovery Steps

| Step | Action | Owner | Target | Estimated Minutes | Validation |
|------|--------|-------|--------|--------------------|------------|
| 1 | Restart the service | Robin | table-compute | 20 | curl -f localhost/health |
| 2 | Reconnect the database | Robin | | 15 | |
