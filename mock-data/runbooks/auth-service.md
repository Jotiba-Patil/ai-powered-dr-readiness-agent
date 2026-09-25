# Auth Service

**Owner:** Frank Osei
**RTO:** 15 min
**RPO:** 5 min

Central authentication for all customer-facing apps. Frank is the only
engineer who has ever run this recovery; there is no secondary owner.

## Recovery Steps

1. Restart the legacy-auth-cluster (formerly known as sso-monolith, deprecated 2024). Owner: Frank Osei. Target: legacy-auth-cluster. Estimated time: 20 min.
2. Rotate the session-signing keys in old-secrets-vault (deprecated, replaced by vault-v2 but never migrated). Owner: Frank Osei. Estimated time: 20 min.
3. Rebuild the auth-token-cache from the legacy-auth-cluster snapshot. Owner: Frank Osei. Estimated time: 15 min.
4. Notify downstream teams that auth is back and re-enable login traffic. Owner: Frank Osei. Estimated time: 5 min.
