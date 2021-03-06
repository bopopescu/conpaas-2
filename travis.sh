#!/bin/sh

set -e 

COVERAGE="`which python-coverage || true`"

if [ -z "$COVERAGE" ]
then
    COVERAGE="`which coverage`"
fi

cd $CI_HOME/conpaas-services/src
python setup.py install

cd $CI_HOME/conpaas-client
python setup.py install

cd $CI_HOME/conpaas-director

# Create fake files/directories not really needed for unit testing
touch ConPaaS.tar.gz
mkdir conpaas
cp -a ../conpaas-services/config conpaas
cp -a ../conpaas-services/scripts conpaas

mkdir -p cpsdirectorconf/certs

# We cannot use system-wide directories
sed -i s#/etc/cpsdirector#$PWD/cpsdirectorconf# director.cfg.example
mkdir -p $PWD/cpsdirectorconf/data

python setup.py install || true

export DIRECTOR_TESTING=true

# Create certificates
python cpsconf.py localhost

# Fake tarball
touch cpsdirectorconf/ConPaaS.tar.gz

$COVERAGE run --source=cpsdirector test.py
$COVERAGE report -m

cd ..
# end of conpaas director unit tests

# conpaas-services unit tests
cd conpaas-services/src/tests/
./unit-tests.sh
cd ../../..

# cps-tools unit tests
cd cps-tools
./unit-tests.sh
cd ..

