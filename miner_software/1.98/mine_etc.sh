#!/bin/bash

#################################
## Begin of user-editable part ##
#################################

POOL=stratum+tcp://stratum-etc.antpool.com:8008
WALLET=0x91109d3C865971DdC7566A9D85A803a74e003ACB.SubAyroWorker01

#################################
##  End of user-editable part  ##
#################################

cd "$(dirname "$0")"

./lolMiner --algo ETCHASH --pool $POOL --user $WALLET $@
