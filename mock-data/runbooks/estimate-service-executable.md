# Estimate Service

**Owner:** Alice Chen
**RTO:** 60 min
**RPO:** 15 min

The Estimate Service computes shipping quotes for the checkout flow. This
runbook restores it after a full regional outage. Every step carries tool-call
annotations for the bundled `drsim` mock MCP server, so it can be executed
step by step with human approval (see docs/design/runbook-execution.md).

## Dependencies

| Name | Type | Critical |
|------|------|----------|
| estimate-postgres | database | yes |
| pricing-cache | database | yes |
| rates-kafka-topic | messaging | no |
| internal-dns | network | yes |

## Recovery Steps

1. Confirm the outage scope in the status dashboard. **Owner:** Alice Chen. Estimated time: 5 min. `curl -sf https://status.internal/estimate-service`
   - Tool: `drsim/k8s_rollout_status {"deployment": "estimate-service", "region": "primary"}`
2. Restart the estimate-service compute nodes in the standby region. **Owner:** Bob Nguyen. Target: standby-region-compute. Estimated time: 15 min. `kubectl rollout status deploy/estimate-service`
   - Tool: `drsim/k8s_rollout_restart {"deployment": "estimate-service", "region": "standby"}`
   - Verify-Tool: `drsim/k8s_rollout_status {"deployment": "estimate-service", "region": "standby", "expect_ready": true}`
   - Rollback-Tool: `drsim/k8s_rollout_undo {"deployment": "estimate-service", "region": "standby"}`
3. Promote the estimate-postgres replica and confirm it accepts writes (after step 1). **Owner:** Priya Iyer. Estimated time: 10 min. `psql -h estimate-postgres -c "select pg_is_in_recovery();"`
   - Tool: `drsim/db_promote_replica {"cluster": "estimate-postgres"}`
   - Verify-Tool: `drsim/db_is_in_recovery {"cluster": "estimate-postgres", "expect_in_recovery": false}`
4. Warm pricing-cache from the last snapshot (after step 3). **Owner:** Bob Nguyen. Estimated time: 15 min. `redis-cli -h pricing-cache ping`
   - Tool: `drsim/cache_warm_from_snapshot {"cache": "pricing-cache", "snapshot": "latest"}`
   - Verify-Tool: `drsim/cache_ping {"cache": "pricing-cache"}`
5. Flip traffic to the standby region and run the smoke test suite (after step 2 and step 4). **Owner:** Alice Chen. Estimated time: 10 min. `make smoke-test REGION=standby`
   - Tool: `drsim/dns_switch_region {"service": "estimate-service", "region": "standby"}`
   - Verify-Tool: `drsim/smoke_run {"service": "estimate-service", "region": "standby"}`
   - Rollback-Tool: `drsim/dns_switch_region {"service": "estimate-service", "region": "primary"}`

## Rollback

If the smoke tests fail, revert DNS to the primary region and re-open the
incident. Owner: Alice Chen. Estimated time: 5 min.
