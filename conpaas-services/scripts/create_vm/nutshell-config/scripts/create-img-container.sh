#!/bin/bash -e
# Copyright (c) 2010-2012, Contrail consortium.
# All rights reserved.
#
# Redistribution and use in source and binary forms, 
# with or without modification, are permitted provided
# that the following conditions are met:
#
#  1. Redistributions of source code must retain the
#     above copyright notice, this list of conditions
#     and the following disclaimer.
#  2. Redistributions in binary form must reproduce
#     the above copyright notice, this list of 
#     conditions and the following disclaimer in the
#     documentation and/or other materials provided
#     with the distribution.
#  3. Neither the name of the Contrail consortium nor the
#     names of its contributors may be used to endorse
#     or promote products derived from this software 
#     without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
# CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, 
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR 
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS 
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
# OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

##
# This script generates a VM image for ConPaaS, to be used for OpenNebula with KVM.
# The script should be run on a Debian or Ubuntu system.
# Before running this script, please make sure that you have the following
# executables in your $PATH:
#
# dd parted losetup kpartx mkfs.ext3 tune2fs mount debootstrap chroot umount grub-install (grub2)
# 
# NOTE: This script requires the installation of Grub 2 (we recommend Grub 1.98 or newer,
# as we experienced problems with 1.96). 
##

##### TO CUSTOMIZE: #####

# The name and size of the image file that will be generated.
FILENAME=conpaas.img
FILESIZE=2048 #MB

# The Debian distribution that you would like to have installed (we recommend squeeze).
DEBIAN_DIST=squeeze
DEBIAN_MIRROR=http://ftp.nl.debian.org/debian

#DEBIAN_DIST=precise
#DEBIAN_MIRROR=http://nl.archive.ubuntu.com/ubuntu/

# The architecture and kernel version for the OS that will be installed (please make
# sure to modify the kernel version name accordingly if you modify the architecture).
ARCH=amd64
KERNEL_VERSION=2.6.32-5-amd64

# Services that will be installed:
PHP_SERVICE=true
MYSQL_SERVICE=true
IPOP_SERVICE=true
GIT_SERVICE=true
SELENIUM_SERVICE=true
HADOOP_SERVICE=true
SCALARIS_SERVICE=true
XTREEMFS_SERVICE=true
CDS_SERVICE=true
HTCONDOR_SERVICE=true
# BLUE_PRINT_INSERT_SERVICE             do not remove this line: it is a placeholder for installing new services

# override above values with those found in config file, if present 
[ -f services_config.cfg ] && . services_config.cfg

#########################
export LC_ALL=C

# Function for displaying highlighted messages.
function cecho() {
  echo -en "\033[1m"
  echo -n "#" $@
  echo -e "\033[0m"
}

# Set up message on purpose before root permission check
cecho "Setting up for these services:"
for i in PHP MYSQL CONDOR IPOP GIT SELENIUM HADOOP SCALARIS XTREEMFS CDS HTCONDOR # BLUE_PRINT_FOR       do not remove this comment: it is a placeholder for installing new services
do
        name=`echo $i`_SERVICE
        eval serv=\${$name}
        $serv && cecho "-" "$i"
done

if [ `id -u` -ne 0 ]; then
  cecho 'need root permissions for this script';
  exit 1;
fi

# System rollback function
function cleanup() {
    # Set errormsg if something went wrong
    [ $? -ne 0 ] && errormsg="Script terminated with errors"

    for mpoint in /dev/pts /dev /proc /
    do
      mpoint="${ROOT_DIR?:not set}${mpoint}"

      # Only attempt to umount $ROOT_DIR{/dev/pts,/dev,/proc,/} if necessary
      if [ -d $mpoint ]
      then
        cecho "Umounting $mpoint"
        umount $mpoint || true
      fi
    done

    sleep 1s
    losetup -d $LOOP_DEV
    sleep 1s
    rm -r $ROOT_DIR
    # Print "Done" on success, $errormsg otherwise
    cecho "${errormsg:-Done}"
}

# Check if required binaries are in $PATH
for bin in dd parted losetup kpartx mkfs.ext3 tune2fs mount debootstrap chroot umount grub-install
do
  if [ -z `which $bin` ]
  then
    if [ -x /usr/lib/command-not-found ]
    then
      /usr/lib/command-not-found $bin
    else
      echo "$bin: command not found"
    fi
    exit 1
  fi
done

cecho "Creating empty disk image at" $FILENAME
dd if=/dev/zero of=$FILENAME bs=1M count=$FILESIZE


LOOP_DEV=`losetup -f`
cecho "Going to use" $LOOP_DEV
losetup $LOOP_DEV $FILENAME


cecho "Creating ext3 filesystem"
echo 'y' | mkfs.ext3 $FILENAME
tune2fs $FILENAME -L root

ROOT_DIR=`mktemp -d`
cecho "Using $ROOT_DIR as mount point"

cecho "Mounting disk image"

mount $LOOP_DEV $ROOT_DIR

# Always clean up on exit
trap "cleanup" EXIT

cecho "Starting debootstrap"
debootstrap --arch $ARCH --include locales $DEBIAN_DIST $ROOT_DIR $DEBIAN_MIRROR

#cecho "Writing fstab"
#echo "/dev/sda1 / ext3 defaults 0 1" > $ROOT_DIR/etc/fstab
cecho "Writing /etc/network/interfaces"
cat <<EOF > $ROOT_DIR/etc/network/interfaces
auto lo
iface lo inet loopback
auto eth0
iface eth0 inet dhcp
EOF
cecho "Removing udev persistent rules"
rm $ROOT_DIR/etc/udev/rules.d/70-persistent* || true

cecho "Changing hostname"
cat <<EOF > $ROOT_DIR/etc/hostname
conpaas
EOF

sed -i '1i 127.0.0.1  conpaas' $ROOT_DIR/etc/hosts

# mount /dev/pts to avoid error message: Can not write log, openpty() failed (/dev/pts not mounted?) 
cecho "Mounting /dev, /dev/pts and /proc in chroot"
mount -obind /dev $ROOT_DIR/dev
mount -obind /dev/pts $ROOT_DIR/dev/pts
mount -t proc proc $ROOT_DIR/proc

cecho "Setting keyboard layout"
chroot $ROOT_DIR /bin/bash -c "echo 'debconf keyboard-configuration/variant  select  USA' | debconf-set-selections"

cecho "Generating and setting locale"
chroot $ROOT_DIR /bin/bash -c "sed --in-place 's/^# en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen"
chroot $ROOT_DIR /bin/bash -c 'locale-gen'
chroot $ROOT_DIR /bin/bash -c 'update-locale LANG=en_US.UTF-8'

cecho "Running apt-get update"
chroot $ROOT_DIR /bin/bash -c 'apt-get -y update'

# disable auto start after package install
cat <<EOF > $ROOT_DIR/usr/sbin/policy-rc.d
#!/bin/sh
exit 101
EOF
chmod 755 $ROOT_DIR/usr/sbin/policy-rc.d

# Generate a script that will install the dependencies in the system. 
cat <<EOF > $ROOT_DIR/conpaas_install
#!/bin/bash
# Function for displaying highlighted messages.
function cecho() {
  echo -en "\033[1m"
  echo -n "#" \$@
  echo -e "\033[0m"
}

# set root passwd
echo "root:conpaas" | chpasswd

# fix apt sources
sed --in-place 's/main/main contrib non-free/' /etc/apt/sources.list

# install dependencies
apt-get -y update
# pre-accept sun-java6 licence
echo "debconf shared/accepted-sun-dlj-v1-1 boolean true" | debconf-set-selections
DEBIAN_FRONTEND=noninteractive apt-get -y --force-yes --no-install-recommends --no-upgrade \
        install openssh-server curl \
        python python-pycurl python-openssl python-m2crypto \
        python-mysqldb python-cheetah python-netaddr nginx \
        tomcat6-user memcached mysql-server \
        ganglia-monitor gmetad rrdtool logtail \
        make gcc g++ sun-java6-jdk erlang ant libxslt1-dev yaws subversion git \
        xvfb xinit unzip automake bc
update-rc.d memcached disable
update-rc.d nginx disable
update-rc.d yaws disable
update-rc.d mysql disable
update-rc.d gmetad disable
update-rc.d ganglia-monitor disable

# create directory structure
echo > /var/log/cpsagent.log
mkdir /etc/cpsagent/
mkdir /var/tmp/cpsagent/
mkdir /var/run/cpsagent/
mkdir /var/cache/cpsagent/
echo > /var/log/cpsmanager.log
mkdir /etc/cpsmanager/
mkdir /var/tmp/cpsmanager/
mkdir /var/run/cpsmanager/
mkdir /var/cache/cpsmanager/

EOF


!($PHP_SERVICE || $MYSQL_SERVICE) && echo 'cecho "===== Skipped PHP & MYSQL ====="' >> $ROOT_DIR/conpaas_install
($PHP_SERVICE || $MYSQL_SERVICE) && cat <<EOF >> $ROOT_DIR/conpaas_install
cecho "===== add dotdeb repo for php fpm ====="
# add dotdeb repo for php fpm
echo "deb http://packages.dotdeb.org $DEBIAN_DIST all" >> /etc/apt/sources.list
wget -O - http://www.dotdeb.org/dotdeb.gpg 2>/dev/null | apt-key add -
apt-get -y update
apt-get -f -y --no-install-recommends --no-upgrade install php5-fpm php5-curl \
              php5-mcrypt php5-mysql php5-odbc \
              php5-pgsql php5-sqlite php5-sybase php5-xmlrpc php5-xsl \
              php5-adodb php5-memcache php5-gd
update-rc.d php5-fpm disable

# remove dotdeb repo
sed --in-place "s%deb http://packages.dotdeb.org $DEBIAN_DIST all%%" /etc/apt/sources.list
apt-get -y update

# remove cached .debs from /var/cache/apt/archives to save disk space
apt-get clean
EOF

$HTCONDOR_SERVICE || echo 'cecho "===== Skipped HTCONDOR ====="' >> $ROOT_DIR/conpaas_install
$HTCONDOR_SERVICE && cat <<EOF >> $ROOT_DIR/conpaas_install
cecho "===== install packages required by HTCondor ====="
mkdir -p /var/lib/condor
chown condor /var/lib/condor
chgrp condor /var/lib/condor
chmod 766 /var/lib/condor
# avoid warning: W: GPG error: http://mozilla.debian.net squeeze-backports Release: The following signatures couldn't be verified because the public key is not available: NO_PUBKEY 85A3D26506C4AE2A 
#apt-get install debian-keyring
wget -O - -q http://mozilla.debian.net/archive.asc | apt-key add -
# avoid warning: W: GPG error: http://dl.google.com stable Release: The following signatures couldn't be verified because the public key is not available: NO_PUBKEY A040830F7FAC5991 
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -

# If things go wrong, you may want to read  http://research.cs.wisc.edu/htcondor/debian/
# 
echo "deb http://research.cs.wisc.edu/htcondor/debian/stable/ $DEBIAN_DIST contrib" >> /etc/apt/sources.list
apt-get update
apt-get -f -y --force-yes install condor
echo ===== check if HTCondor is running =====
ps -ef | grep condor
echo ===== stop condor =====
/etc/init.d/condor stop
echo ===== 

# remove cached .debs from /var/cache/apt/archives to save disk space
apt-get clean
EOF

$IPOP_SERVICE || echo 'cecho "===== Skipped IPOP ====="' >> $ROOT_DIR/conpaas_install
$IPOP_SERVICE && cat <<EOF >> $ROOT_DIR/conpaas_install
cecho "===== install IPOP package ====="
echo "deb http://www.grid-appliance.org/files/packages/deb/ stable contrib" >> /etc/apt/sources.list
wget -O - http://www.grid-appliance.org/files/packages/deb/repo.key | apt-key add -
apt-get update
apt-get -f -y install ipop

# remove cached .debs from /var/cache/apt/archives to save disk space
apt-get clean

EOF

$GIT_SERVICE || echo 'cecho "===== Skipped GIT ====="' >> $ROOT_DIR/conpaas_install
$GIT_SERVICE && cat <<EOF >> $ROOT_DIR/conpaas_install
cecho "===== install GIT ====="
# add git user
useradd git --shell /usr/bin/git-shell --create-home -k /dev/null
# create ~git/.ssh and authorized_keys
install -d -m 700 --owner=git --group=git /home/git/.ssh 
install -m 600 --owner=git --group=git /dev/null ~git/.ssh/authorized_keys 
# create default repository
git init --bare ~git/code
# create SSH key for manager -> agent access
ssh-keygen -N "" -f ~root/.ssh/id_rsa
echo StrictHostKeyChecking no > ~root/.ssh/config
# allow manager -> agent passwordless pushes 
cat ~root/.ssh/id_rsa.pub > ~git/.ssh/authorized_keys
# fix repository permissions
chown -R git:git ~git/code

EOF

$SELENIUM_SERVICE || echo 'cecho "===== Skipped SELENIUM ====="' >> $ROOT_DIR/conpaas_install
$SELENIUM_SERVICE && cat <<EOF >> $ROOT_DIR/conpaas_install
cecho "===== install SELENIUM ====="
# recent versions of iceweasel and chrome
echo "deb http://backports.debian.org/debian-backports $DEBIAN_DIST-backports main" >> /etc/apt/sources.list
echo "deb http://mozilla.debian.net/ $DEBIAN_DIST-backports iceweasel-esr" >> /etc/apt/sources.list
echo "deb http://dl.google.com/linux/deb/ stable main" >> /etc/apt/sources.list
    
apt-get -y update
apt-get -f -y --force-yes install -t $DEBIAN_DIST-backports iceweasel
apt-get -f -y --force-yes install google-chrome-stable

EOF

$HADOOP_SERVICE || echo 'cecho "===== Skipped HADOOP ====="' >> $ROOT_DIR/conpaas_install
$HADOOP_SERVICE && cat <<EOF >> $ROOT_DIR/conpaas_install
cecho "===== install cloudera repo for hadoop ====="
# add cloudera repo for hadoop
echo "deb http://archive.cloudera.com/debian $DEBIAN_DIST-cdh3 contrib" >> /etc/apt/sources.list
wget -O - http://archive.cloudera.com/debian/archive.key 2>/dev/null | apt-key add -
apt-get -y update
apt-get -f -y --no-install-recommends --no-upgrade install \
  hadoop-0.20 hadoop-0.20-namenode hadoop-0.20-datanode \
  hadoop-0.20-secondarynamenode hadoop-0.20-jobtracker  \
  hadoop-0.20-tasktracker hadoop-pig hue-common  hue-filebrowser \
  hue-jobbrowser hue-jobsub hue-plugins hue-server dnsutils
update-rc.d hadoop-0.20-namenode disable
update-rc.d hadoop-0.20-datanode disable
update-rc.d hadoop-0.20-secondarynamenode disable
update-rc.d hadoop-0.20-jobtracker disable
update-rc.d hadoop-0.20-tasktracker disable
update-rc.d hue disable
# create a default config dir
mkdir -p /etc/hadoop-0.20/conf.contrail
update-alternatives --install /etc/hadoop-0.20/conf hadoop-0.20-conf /etc/hadoop-0.20/conf.contrail 99
# remove cloudera repo
sed --in-place "s%deb http://archive.cloudera.com/debian $DEBIAN_DIST-cdh3 contrib%%" /etc/apt/sources.list
apt-get -y update


EOF

$SCALARIS_SERVICE || echo 'cecho "===== Skipped SCALARIS ====="' >> $ROOT_DIR/conpaas_install
$SCALARIS_SERVICE && cat <<EOF >> $ROOT_DIR/conpaas_install
cecho "===== install scalaris repo ====="
# add scalaris repo
echo "deb http://download.opensuse.org/repositories/home:/scalaris/Debian_6.0 /" >> /etc/apt/sources.list
wget -O - http://download.opensuse.org/repositories/home:/scalaris/Debian_6.0/Release.key 2>/dev/null | apt-key add -
apt-get -y update
apt-get -f -y --no-install-recommends --no-upgrade install scalaris screen
update-rc.d scalaris disable
# remove scalaris repo
sed --in-place 's%deb http://download.opensuse.org/repositories/home:/scalaris/Debian_6.0 /%%' /etc/apt/sources.list
apt-get -y update

EOF

$XTREEMFS_SERVICE || echo 'cecho "===== Skipped XTREEMFS ====="' >> $ROOT_DIR/conpaas_install
$XTREEMFS_SERVICE && cat <<EOF >> $ROOT_DIR/conpaas_install
cecho "===== install xtreemfs repo ====="
# add xtreemfs repo
echo "deb http://download.opensuse.org/repositories/home:/xtreemfs:/unstable/Debian_6.0 /" >> /etc/apt/sources.list
wget -O - http://download.opensuse.org/repositories/home:/xtreemfs:/unstable/Debian_6.0/Release.key 2>/dev/null | apt-key add -
apt-get -y update
apt-get -f -y --no-install-recommends --no-upgrade install xtreemfs-server xtreemfs-client xtreemfs-tools
update-rc.d xtreemfs-osd disable
update-rc.d xtreemfs-mrc disable
update-rc.d xtreemfs-dir disable
# remove xtreemfs repo
sed --in-place 's%deb http://download.opensuse.org/repositories/home:/xtreemfs:/unstable/Debian_6.0 /%%' /etc/apt/sources.list
apt-get -y update

EOF

$CDS_SERVICE || echo 'cecho "===== Skipped CDS ====="' >> $ROOT_DIR/conpaas_install
$CDS_SERVICE && cat <<EOF >> $ROOT_DIR/conpaas_install
cecho "===== install latest nginx (1.2.2) and other packages required by CDS ====="
# install latest nginx (1.2.2) and other packages required by CDS
DEBIAN_FRONTEND=noninteractive apt-get -y --force-yes --no-install-recommends --no-upgrade \
    install libpcre3-dev libssl-dev libgeoip-dev libperl-dev
wget http://nginx.org/download/nginx-1.2.2.tar.gz
tar xzf nginx-1.2.2.tar.gz
cd nginx-1.2.2
./configure --sbin-path=/usr/sbin/nginx --conf-path=/etc/nginx/nginx.conf --error-log-path=/var/log/nginx/error.log --http-client-body-temp-path=/var/lib/nginx/body --http-fastcgi-temp-path=/var/lib/nginx/fastcgi --http-log-path=/var/log/nginx/access.log --http-proxy-temp-path=/var/lib/nginx/proxy --lock-path=/var/lock/nginx.lock --pid-path=/var/run/nginx.pid --with-debug --with-http_dav_module --with-http_flv_module --with-http_geoip_module --with-http_gzip_static_module --with-http_realip_module --with-http_stub_status_module --with-http_ssl_module --with-http_sub_module --with-ipv6 --with-mail --with-mail_ssl_module --with-http_perl_module
make
make install
cd ..
rm -rf nginx-1.2.2*

EOF

# BLUE_PRINT_INSERT_SOFTWARE            do not remove this line: it is a placeholder for installing new services

cat <<EOF >> $ROOT_DIR/conpaas_install
apt-get -y clean
exit 0
EOF

# Execute the script for installing the dependencies.
chmod a+x $ROOT_DIR/conpaas_install
chroot $ROOT_DIR /bin/bash /conpaas_install
rm -f $ROOT_DIR/conpaas_install

rm -f $ROOT_DIR/usr/sbin/policy-rc.d
## install ec2 startup scripts
{
cat <<_EOF_
#!/bin/bash
### BEGIN INIT INFO
# Provides:          ec2-get-credentials
# Required-Start:    \$remote_fs
# Required-Stop:
# Should-Start:
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Retrieve the ssh credentials and add to authorized_keys
# Description:
#
### END INIT INFO
_EOF_
wget -O - https://ec2ubuntu.googlecode.com/svn/trunk/etc/init.d/ec2-get-credentials
} >$ROOT_DIR/etc/init.d/ec2-get-credentials

{
cat <<_EOF_
#!/bin/sh
### BEGIN INIT INFO
# Provides:          ec2-ssh-host-key-gen
# Required-Start:    \$remote_fs
# Required-Stop:
# Should-Start:      sshd
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Generate new ssh host keys on first boot
# Description:       Re-generates the ssh host keys on every
#                    new instance (i.e., new AMI). If you want
#                    to keep the same ssh host keys for rebundled
#                    AMIs, then disable this before rebundling
#                    using a command like:
#                       rm -f /etc/rc?.d/S*ec2-ssh-host-key-gen
#
### END INIT INFO
_EOF_
wget -O - https://ec2ubuntu.googlecode.com/svn/trunk/etc/init.d/ec2-ssh-host-key-gen
} >$ROOT_DIR/etc/init.d/ec2-ssh-host-key-gen

{
cat <<_EOF_
#!/bin/bash
### BEGIN INIT INFO
# Provides:          ec2-run-user-data
# Required-Start:    \$all
# Required-Stop:
# Should-Start:
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Run instance user-data if it looks like a script.
# Description:       Only retrieves and runs the user-data script once per
#                    instance. If you want the user-data script to run again
#                    (e.g., on the next boot) then add this command in the
#                    user-data script:
#                    rm -f /var/ec2/ec2-run-user-data.*
### END INIT INFO
_EOF_
wget -O - https://ec2ubuntu.googlecode.com/svn/trunk/etc/init.d/ec2-run-user-data
} >$ROOT_DIR/etc/init.d/ec2-run-user-data

## fix gzip detection in ec2-run-user-data
## "file -bi" output looks like "application/x-gzip; charset=binary"
## "file -b --mime-type" output looks like "application/x-gzip"
sed -i -e 's/$(file -bi /$(file -b --mime-type /' $ROOT_DIR/etc/init.d/ec2-run-user-data

## enable ec2 startup scripts
chmod a+x $ROOT_DIR/etc/init.d/ec2-*
chroot $ROOT_DIR /usr/sbin/update-rc.d ec2-get-credentials defaults
chroot $ROOT_DIR /usr/sbin/update-rc.d ec2-ssh-host-key-gen defaults
chroot $ROOT_DIR /usr/sbin/update-rc.d ec2-run-user-data defaults



