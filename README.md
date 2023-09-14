# Minimal reproduction code for a clickhouse issue related to Distributed+Replicated+MaterializedView

This is a minimal docker-compose stack to reproduce a weird behavior/"bug" we observed when combining
Clickhouse `Distributed` tables to `Replicated...` tables for which a `Materialized View` that compute some basic aggregates (*e.g.*, sums) is setup.

1. INSERTING to the `Distributed` table, then SELECTing the overall counts from the input table and the MV's aggregated sums, we see that the counts are completely broken :
````
./it_fails.sh
````

2. If, instead, we INSERT to local `Replicated...` tables at random nodes (mimicking, *e.g.*, an HAProxy round robin loadbalancing) all the counts are perfectly correct in both the input tables and the MV's aggregates
````
./it_works.sh
````

As you can see in `main.py` the only change between `./it_fails.sh` and `./it_works.sh` is in the `USE_DISTRIBUTED` flag that either choose the Distributed table as the INSERT point or a randomly picked node's local  `ReplicatedAggregatingMergeTree` table.


> It is still unclear to us if it's a bug, a feature, a bad configuration from our reproduction example or a misuse of Clickhouse engines.

Thanks for your help in solving this issue !