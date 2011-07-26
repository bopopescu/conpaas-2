'''
Created on Mar 9, 2011

@author: ielhelw
'''
from BaseHTTPServer import HTTPServer

import memcache, httplib, inspect
from conpaas.iaas import IaaSClient
from conpaas.web.http import AbstractRequestHandler
from conpaas import log


class ManagerRequestHandler(AbstractRequestHandler):
  
  def _render_arguments(self, method, params):
    ret = '<p>Arguments:<table>'
    ret += '<tr><th>Method</th><td>' + method + '</td></tr>'
    for param in params:
      if isinstance(params[param], dict):
        ret += '<tr><th>' + param + '</th><td>Contents of: ' + params[param].filename + '</td></tr>'
      else:
        ret += '<tr><th>' + param + '</th><td>' + params[param] + '</td></tr>'
    ret += '</table></p>'
    return ret
  
  def send_action_missing(self, method, params):
    self.send_custom_response(httplib.BAD_REQUEST, '''<html>
<head>
<title>BAD REQUEST</title>
</head>
<body>
<h1>ConPaaS PHP</h1>
<p>No "action" specified.</p>
<p>This URL is used to access the service manager directly.
You may want to copy-paste the URL as a parameter to the 'managerc.py' command-line utility.</p>
''' + self._render_arguments(method, params) + '</body></html>')
  
  def send_action_not_found(self, method, params):
    self.send_custom_response(httplib.NOT_FOUND, '''<html>
<head>
<title>ACTION NOT FOUND</title>
</head>
<body>
<h1>ConPaaS PHP</h1>
<p>The specified "action" was not found.</p>
<p>You may want to review the list of supported actions provided by the 'managerc.py' command-line utility.</p>
''' + self._render_arguments(method, params) + '</body></html>')


class DeploymentManager(HTTPServer):
  def __init__(self,
               server_address,
               config_parser,
               scalaris_addr,
               reset_config=False,
               RequestHandlerClass=ManagerRequestHandler):
    HTTPServer.__init__(self, server_address, RequestHandlerClass)
    log.init(config_parser)
    # init configuration storage and iaas
    self.memcache = memcache.Client([config_parser.get('manager', 'MEMCACHE_ADDR')])
    self.iaas = IaaSClient(config_parser)
    self.scalaris_addr = scalaris_addr
    self.reset_config = reset_config
    self.config_parser = config_parser
    
    if hasattr(self, '_create_%s_service' % (config_parser.get('manager', 'TYPE').lower())):
      func = getattr(self, '_create_%s_service' % (config_parser.get('manager', 'TYPE').lower()))
      if inspect.ismethod(func):
        func()
      else: raise Exception('manager TYPE was not set correctly')
    else: raise Exception('manager TYPE was not set correctly')
    
    from conpaas.web.manager import config
    config.memcache = self.memcache
    config.iaas = self.iaas
    self.callback_dict = {'GET': {}, 'POST': {}, 'UPLOAD': {}}
    
    for http_method in self.conpaas_implementation.exposed_functions:
      for func_name in self.conpaas_implementation.exposed_functions[http_method]:
        self.register_method(http_method, func_name, self.conpaas_implementation.exposed_functions[http_method][func_name])
  
  def _create_php_service(self):
    from conpaas.web.manager.internal import php
    self.conpaas_implementation = php.PHPInternal(
                                self.memcache,
                                self.iaas,
                                self.config_parser.get('manager', 'CODE_REPO'),
                                self.config_parser.get('manager', 'LOG_FILE'),
                                self.scalaris_addr,
                                self.reset_config)
  
  def _create_java_service(self):
    from conpaas.web.manager.internal import java
    self.conpaas_implementation = java.JavaInternal(
                            self.memcache,
                            self.iaas,
                            self.config_parser.get('manager', 'CODE_REPO'),
                            self.config_parser.get('manager', 'LOG_FILE'),
                            self.reset_config)
  
  def register_method(self, http_method, func_name, callback):
    self.callback_dict[http_method][func_name] = callback
