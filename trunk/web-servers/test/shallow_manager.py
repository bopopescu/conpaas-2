'''
Created on Mar 30, 2011

@author: ielhelw
'''

import sys
import memcache
from tempfile import mkdtemp
from os import mkdir
from os.path import join
from threading import Thread

from mock import agentClient
from mock.iaas import IaaSClient
from optparse import OptionParser
from ConfigParser import ConfigParser


parser = OptionParser()
parser.add_option('-p', '--port', type='int', dest='port', default=None)
parser.add_option('-m', '--memcacheport', type='int', dest='mc', default=None)
parser.add_option('-l', '--logfile', type='string', dest='logfile', default=None)
parser.add_option('-t', '--type', type='choice', dest='type', choices=['PHP', 'JAVA'], default='PHP')
opts, args = parser.parse_args()
#parser.check_choice()

if not opts.port or not opts.mc or not opts.logfile:
  parser.print_help()
  sys.exit(1)

tdir = mkdtemp(prefix='conpaas-web-manager-', dir='/tmp')
print tdir
code_repo = join(tdir, 'code-repo')
mkdir(code_repo)

config_parser = ConfigParser()
config_parser.add_section('manager')
config_parser.set('manager', 'LOG_FILE', opts.logfile)
config_parser.set('manager', 'MEMCACHE_ADDR', 'localhost:'+str(opts.mc))
config_parser.set('manager', 'CODE_REPO', code_repo)
config_parser.set('manager', 'TYPE', opts.type)

from conpaas import log
log.init(config_parser)

# PATCH the real implementations with mock
from conpaas.web.manager import server, internal
server.IaaSClient = IaaSClient
internal.client = agentClient
if config_parser.get('manager', 'TYPE') == 'PHP':
  from conpaas.web.manager.internal import php
  from conpaas.web.manager.config import PHPServiceConfiguration
  php.client = agentClient
  ConfigurationToUse = PHPServiceConfiguration
elif config_parser.get('manager', 'TYPE') == 'JAVA':
  from conpaas.web.manager.internal import java
  from conpaas.web.manager.config import JavaServiceConfiguration
  java.client = agentClient
  ConfigurationToUse = JavaServiceConfiguration
else:
  raise Exception('Did not set manager TYPE')

mc = memcache.Client(['localhost:'+str(opts.mc)])
mc.set(internal.InternalsBase.CONFIG, ConfigurationToUse())
mc.set(internal.InternalsBase.DEPLOYMENT_STATE, internal.InternalsBase.S_INIT)

server_port = opts.port

server = server.DeploymentManager(('0.0.0.0', server_port), config_parser, '', reset_config=True)
t = Thread(target=server.serve_forever)

t.start()
