#!/bin/sh

if [ `id -u` -ne "0" ]
then
    echo "E: Please run this script as root"
    exit 1
fi

# Installing required Debian packages
apt-get update
apt-get -y --force-yes install build-essential python-setuptools python-dev apache2 libapache2-mod-wsgi libcurl4-openssl-dev ntpdate lynx moreutils python-cheetah

# Reinstalling setuptools (fixes a bug on some upgrade installations)
apt-get -y --force-yes --reinstall install python-setuptools

# Set correct date and time
ntpdate 0.us.pool.ntp.org

# Installing cpsdirector
python setup.py install

# Configuring SSL certificates
cpsconf.py

# Configuring Apache
a2enmod wsgi
a2enmod ssl
a2ensite conpaas-director

# Restarting apache
service apache2 restart
