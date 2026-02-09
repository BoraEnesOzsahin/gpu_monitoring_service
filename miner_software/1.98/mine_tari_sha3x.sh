#!/bin/bash

#################################
## Begin of user-editable part ##
#################################

POOL=de-eu.luckypool.io:6118
WALLET=12Dn9pg3n4FbNSfhT7ibAt3Hk3BjhtXasm2yNSf8cUPXtVSkMYMhCiv56t1P2hyYGwtbmfdkQbAQAuMx21uvbAyFd46.lolMinerWorker
PASS=x

#################################
##  End of user-editable part  ##
#################################

cd "$(dirname "$0")"

./lolMiner -a SHA3X --pool $POOL --user $WALLET --pass $PASS $@
