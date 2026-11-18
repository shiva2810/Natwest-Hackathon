# What-if scenarios

Each file is one event in the same format as `data/events/event_stream.json` (file-level changes:
insert / update / set / append). Apply with the API (`POST /scenarios/<name>`), the client
(`SeamClient().scenario("<name>")`) or `python -m scripts.scenarios <name> [<name> ...]`.
Copy one to make your own.

| File | What it tests | Expected effect |
|---|---|---|
| fix_data_residency | StreamLedger moves processing to Frankfurt | S3 closes (unless VerifyPoint EV-03 is applied) |
| fix_support_capacity | Freeze exception, 3 agents hired | S4 closes (9 agents x 40h = 360 >= 336) |
| fix_change_control | Change control filed, Legal re-approves v2.0 | S5 closes |
| fix_seller_training | Remaining sellers complete PCT-101 | S2 closes |
| general_counsel_resigns | Sofia Marchetti (E003) resigns before launch | NEW S1 seam for E003 (owns change control) |
| decoy_turns_real | Harbor Analytics (US) starts receiving customer data | S3 grows: the decoy becomes a real breach |
| new_seller_untrained | New seller hired, no PCT-101 | S2 grows by one |
