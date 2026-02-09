#!/bin/bash

POOL=tls://pool.woolypooly.com:3136
WALLET=pyrin:qq92h3nryfwq0gkh73cwvjh9hhqlq2mank9sfxtgc99hqwn2ec6u2gszphr0u.checkMe

./lolMiner --algo PYRINV2 --pool $POOL --user $WALLET $@

