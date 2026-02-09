#!/bin/bash

#################################
## Begin of user-editable part ##
#################################

POOL=ctxc.2miners.com:2222
WALLET=0xf685a5Bfb1a3b9B2bEbbD6D6f3E196B89e275560.lolMinerWorker

#################################
##  End of user-editable part  ##
#################################

cd "$(dirname "$0")"

./lolMiner --coin CTXC --pool $POOL --user $WALLET $@
