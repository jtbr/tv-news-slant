#!/bin/bash
# run genTopPhrases for all the months in the given year
# to capture logs: genTopPhrasesMonthly.sh [year] | tee genTopPhrases-yearmonthly.log 2>&1
if [[ $# -lt 1 ]]; then
    echo "usage: genTopPhrasesMonthly.sh [year]"
    exit
fi
for i in $(seq -f "%02g" 1 12)
do
    echo "Running genTopPhrases on $1-$i..."
    unbuffer python genTopPhrases.py $1 $i
done