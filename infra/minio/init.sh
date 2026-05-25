#!/bin/sh
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/novel2drama --ignore-existing
