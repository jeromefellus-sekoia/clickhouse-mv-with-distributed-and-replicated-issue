import datetime
import os
from random import choice, randint
from time import sleep
import time
from clickhouse_driver import Client

clickhouse1 = Client(host="clickhouse1", port=9000, user="user", password="plop")
clickhouse2 = Client(host="clickhouse2", port=9000, user="user", password="plop")
clickhouse3 = Client(host="clickhouse3", port=9000, user="user", password="plop")

clickhouse1.execute("DROP TABLE IF EXISTS stats_local ON CLUSTER mycluster SYNC")
clickhouse1.execute("DROP TABLE IF EXISTS stats ON CLUSTER mycluster SYNC")
clickhouse1.execute("DROP TABLE IF EXISTS hourly_mv ON CLUSTER mycluster SYNC")
clickhouse1.execute("DROP TABLE IF EXISTS hourly_local ON CLUSTER mycluster SYNC")
clickhouse1.execute("DROP TABLE IF EXISTS hourly ON CLUSTER mycluster SYNC")

# Create the statistic's replicated and sharded storage
clickhouse1.execute(
    """
CREATE TABLE stats_local ON CLUSTER mycluster
(
    `bin` String,
    `time` DateTime,
    `nb` SimpleAggregateFunction(sum, UInt64)
)

ENGINE = ReplicatedMergeTree('/clickhouse/tables/{shard}/stats_local', '{replica}')
ORDER BY (bin, time)
"""
)

# Add a Distributed view in front of it
clickhouse1.execute(
    """
CREATE TABLE stats ON CLUSTER mycluster
(
    `bin` String,
    `time` DateTime,
    `nb` SimpleAggregateFunction(sum, UInt64)
)
ENGINE = Distributed('mycluster', 'default', 'stats_local', rand())
"""
)


# Create the hourly statistics replicated and sharded storage
clickhouse1.execute(
    """
CREATE TABLE hourly_local ON CLUSTER mycluster
(
`bin` String,
`time` DateTime,
`nb` SimpleAggregateFunction(sum, UInt64)
)
ENGINE = ReplicatedAggregatingMergeTree('/clickhouse/tables/{shard}/hourly_local', '{replica}')
ORDER BY (bin, time)
"""
)

# Add a Distributed view in front of it
clickhouse1.execute(
    """
CREATE TABLE hourly ON CLUSTER mycluster
(
`bin` String,
`time` DateTime,
`nb` SimpleAggregateFunction(sum, UInt64)
)
ENGINE = Distributed('mycluster', 'default', 'hourly_local', rand())
"""
)

# Materialized view from statistic to hourly statistic
clickhouse1.execute(
    """
CREATE MATERIALIZED VIEW hourly_mv ON CLUSTER mycluster
TO hourly_local

AS SELECT bin, toStartOfHour(time) as time, sum(nb) as nb FROM stats_local
GROUP BY bin, time
"""
)


START_TS = time.time()
BATCH_SIZE = 1000

USE_DISTRIBUTED = os.getenv("USE_DISTRIBUTED") == "1"

try:
    ground_truth = []
    total = 0
    for i in range(1000):
        batch = [
            (
                choice(["a", "b"]),  # Imagine we have two bins
                datetime.datetime.fromtimestamp(
                    START_TS + (time.time() - START_TS) * 1800
                ),  # 1s of walltime becomes 30min
                randint(1, 5),  # Some random counter
            )
            for _ in range(BATCH_SIZE)
        ]

        if USE_DISTRIBUTED:
            # CASE 1 : Reproduce the "bug"

            # INSERT to the Distributed input table, which will take care of sharding
            clickhouse1.execute(
                "INSERT INTO stats (`bin`,`time`,`nb`) VALUES", batch
            )
        else:
            # CASE 2 : Write directly to local replicated tables

            # Simulate a random loadbalancer to our 3 nodes INSERTING to a LOCAL table on a random node, NOT THE DISTRIBUTED ONE
            choice([clickhouse1, clickhouse2, clickhouse3]).execute(
                "INSERT INTO stats_local (`bin`,`time`,`nb`) VALUES", batch
            )


        total += len(batch)
        ground_truth += batch
        print(total, f"USE_DISTRIBUTED={USE_DISTRIBUTED}", flush=True)
        sleep(0.01)

        if i % 20 == 19:
            # Give clickhouse some time to replicate stuff
            sleep(1)

            # Assert global counts are equal in hourly_stats and stats
            stats = dict(clickhouse1.execute("SELECT bin, sum(nb) FROM stats GROUP BY bin"))
            hourly_stats = dict(clickhouse1.execute("SELECT bin, sum(nb) FROM hourly GROUP BY bin"))
            ground_truth_stats:dict = {}
            for bin, t, nb in ground_truth:
                ground_truth_stats[bin] = ground_truth_stats.get(bin, 0) + nb

            for bin,nb in ground_truth_stats.items():
                assert nb == stats[bin], ":( counts from stats table are incorrect "
            print("🎉 counts from stats table are correct 🎉")

            for bin,nb in ground_truth_stats.items():
                assert nb == hourly_stats[bin],  ":( counts from hourly MV are incorrect "
            print("🎉 counts from hourly MV are correct 🎉") # Won't be executed :(

except KeyboardInterrupt:
    ...
