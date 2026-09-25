# Payment Gateway

`Owner: team`
`RTO: 30 min`
`RPO: 5 min`

Handles card and wallet payment capture. This runbook is known to be rushed;
it was written the week after a real incident and has never been rehearsed.

## Dependencies

- payment-ledger-db (postgres, critical)
- fraud-check-external (third-party)
- card-network-gateway
- legacy-token-vault

## Recovery Steps

1. Fix the database issue. Owner: team. 10 min.
2. Restart the gateway. Owner: team. 10 min.
3. Check the queue backlog and clear it if needed. Owner: Marcus Lee. 5-10 min.
4. Re-enable card processing. Owner: Marcus Lee. 10 min.
5. Tell support the incident is resolved. Owner: Marcus Lee. 5 min.
