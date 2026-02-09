#!/bin/bash

#################################
## Begin of user-editable part ##
#################################

POOL=de.conflux.herominers.com:1170
WALLET=cfx:aajgdgnnt7s4n3hmz457v4530uv0d108xjrprfjyre.lolMinerWorker

#################################
##  End of user-editable part  ##
#################################

cd "$(dirname "$0")"

./lolMiner --algo OCTOPUS --pool $POOL --user $WALLET $@
while [ $? -eq 42 ]; do
    sleep 10s
    ./lolMiner --algo OCTOPUS --pool $POOL --user $WALLET $@
done
