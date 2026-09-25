<!--
Mock runbook: order-service (the "complete reference" runbook).
Purpose: show every field the parser extracts, with health-check API calls as
validation commands. Pair it with inventories/order-service.json.

Intended findings (with inventories/order-service.json, everything UP):
- No rule-based gaps: every step has a named owner, a time estimate and a
  validation command, a Rollback section exists, and every dependency is in
  the inventory.
- RTO feasible: 48 min of work against a 60 min RTO (12 min buffer).
- Explicit ordering via "after step N" phrases gives a multi-phase plan
  even without the LLM (steps 2, 3 and 4 can run in parallel).
- Possible LLM-only observations: Maria Lopez owns both the first and last
  steps, and payment-gateway-api is an external dependency outside our control.
Try: set "mockStatus": "DOWN" on a service in the inventory to see
UNVERIFIED_DEPENDENCY and the impact on the steps that reference it.
-->

# Order Service

**Owner:** Maria Lopez
**RTO:** 60 min
**RPO:** 5 min

The Order Service accepts, prices and persists customer orders. This runbook
fails it over from the primary region (us-east-1) to the standby region
(us-west-2) after a regional outage.

## Dependencies

| Name | Type | Critical |
|------|------|----------|
| orders-postgres | database | yes |
| orders-redis | database | no |
| order-events-kafka | messaging | yes |
| orders-vault | secrets | yes |
| payment-gateway-api | external | yes |
| orders-k8s-standby | compute | yes |
| internal-dns | network | yes |

## Recovery Steps

1. Declare the incident and confirm the outage scope on the status API. **Owner:** Maria Lopez. Target: status-page. Estimated time: 5 min. `curl -sf https://status.internal/api/v1/services/order-service`
2. Confirm orders-vault is unsealed in the standby region so the service can read its secrets (after step 1). **Owner:** Dev Patel. Target: orders-vault. Estimated time: 5 min. `curl -sf https://vault.us-west-2.orders.internal/v1/sys/health`
3. Promote the orders-postgres standby replica to primary (after step 1). **Owner:** Priya Shah. Target: orders-postgres. Estimated time: 10 min. `curl -sf https://orders-postgres.us-west-2.health.internal/healthz`
4. Restore orders-redis from the latest snapshot (after step 1). **Owner:** Tom Becker. Target: orders-redis. Estimated time: 5 min. `curl -sf https://orders-redis.us-west-2.health.internal/healthz`
5. Resume order-events-kafka consumers from the last committed offsets (after step 3). **Owner:** Tom Becker. Target: order-events-kafka. Estimated time: 5 min. `curl -sf https://order-events-kafka.us-west-2.health.internal/healthz`
6. Scale up order-service on orders-k8s-standby and wait for all pods to be ready (after step 2, step 3 and step 4). **Owner:** Dev Patel. Target: orders-k8s-standby. Estimated time: 10 min. `curl -sf https://order-service.us-west-2.internal/healthz`
7. Verify outbound connectivity to payment-gateway-api with a zero-value authorization (after step 6). **Owner:** Priya Shah. Target: payment-gateway-api. Estimated time: 3 min. `curl -sf https://payments.partner.example/v2/health`
8. Switch internal-dns to the standby region and run the order smoke test (after step 5 and step 7). **Owner:** Maria Lopez. Target: internal-dns. Estimated time: 5 min. `curl -sf https://order-service.internal/api/v1/health`

## Rollback

If the smoke test in step 8 fails, revert internal-dns to the primary region,
scale order-service on orders-k8s-standby back to zero, and re-open the
incident. Owner: Maria Lopez. Estimated time: 5 min.
`curl -sf https://order-service.us-east-1.internal/healthz`
