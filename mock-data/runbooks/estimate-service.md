# Estimate Service

**Owner:** Alice Chen
**RTO:** 60 min
**RPO:** 15 min

The Estimate Service computes shipping quotes for the checkout flow. This
runbook restores it after a full regional outage.

## Dependencies

| Name | Type | Critical |
|------|------|----------|
| estimate-postgres | database | yes |
| pricing-cache | database | yes |
| rates-kafka-topic | messaging | no |
| internal-dns | network | yes |

## Recovery Steps

1. Confirm the outage scope in the status dashboard. **Owner:** Alice Chen. Estimated time: 5 min. `curl -sf https://status.internal/estimate-service`
2. Restart the estimate-service compute nodes in the standby region. **Owner:** Bob Nguyen. Target: standby-region-compute. Estimated time: 15 min. `kubectl rollout status deploy/estimate-service`
3. Verify estimate-postgres replica is promoted and accepting writes (after step 1). **Owner:** Priya Iyer. Estimated time: 10 min. `psql -h estimate-postgres -c "select pg_is_in_recovery();"`
4. Warm pricing-cache from the last snapshot (after step 3). **Owner:** Bob Nguyen. Estimated time: 15 min. `redis-cli -h pricing-cache ping`
5. Run the smoke test suite against the standby region and flip traffic over (after step 2 and step 4). **Owner:** Alice Chen. Estimated time: 10 min. `make smoke-test REGION=standby`

## Rollback

If the smoke tests fail, revert DNS to the primary region and re-open the
incident. Owner: Alice Chen. Estimated time: 5 min.
