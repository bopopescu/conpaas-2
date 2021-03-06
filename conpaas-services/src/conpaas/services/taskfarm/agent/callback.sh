#!/bin/bash
# This file should only be called from 
#	./conpaas-services/src/conpaas/services/taskfarm/src/org/koala/runnersFramework/runners/bot/BoTRunner.java 

# TODO   set $CONPAAS_HOME
DATE=" [ `date +'%Y-%m-%d %H:%M:%S %Z'  | tr -d '\012\015'` ]"
echo "$DATE" $0 $@ >> /root/cpsclient.taskfarm.out

case $1 in
        decrementUserCredit)
                AMOUNT=`echo $2 | sed 's/\.0*//'`
                wget --ca-certificate /etc/cpsmanager/certs/ca_cert.pem \
                     --certificate    /etc/cpsmanager/certs/cert.pem \
                     --private-key    /etc/cpsmanager/certs/key.pem \
                     $(awk '/^CREDIT_URL/ { print $3 }' /root/config.cfg) \
                     --post-data "decrement=$AMOUNT" \
                     -O /tmp/cpsclient.taskfarm.out.wget 2>&1 >> /tmp/cpsclient.taskfarm.wget
		cat /tmp/cpsclient.taskfarm.out.wget >> /root/creditor.err
		rm /tmp/cpsclient.taskfarm.out.wget
        ;;
esac

