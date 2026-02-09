#!/bin/bash

#################################
## Begin of user-editable part ##
#################################

POOL=taric29.luckypool.io:3111
WALLET=12Dn9pg3n4FbNSfhT7ibAt3Hk3BjhtXasm2yNSf8cUPXtVSkMYMhCiv56t1P2hyYGwtbmfdkQbAQAuMx21uvbAyFd46.lolMiner
PASS=x

#################################
##  End of user-editable part  ##
#################################

cd "$(dirname "$0")"

./lolMiner -a CR29 --pool $POOL --user $WALLET --pass $PASS $@
