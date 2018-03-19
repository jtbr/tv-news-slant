#!/bin/bash
# run parseCR for all the months in the given year
# be sure "REBUILD_DATA" is False when running in this way.
# to capture logs: parseCRmonths.sh [year] | tee parseCR-yearmonthly.log 2>&1
if [[ $# -lt 1 ]]; then
    echo "usage: parseCRmonths.sh [year]"
    exit
fi
for i in $(seq -f "%02g" 1 12)
do
    echo "Running parseCR on $1-$i..."
    unbuffer python parseCR.py $1 $i
done