'''
Copyright (c) 2010-2012, Contrail consortium.
All rights reserved.

Redistribution and use in source and binary forms, 
with or without modification, are permitted provided
that the following conditions are met:

 1. Redistributions of source code must retain the
    above copyright notice, this list of conditions
    and the following disclaimer.
 2. Redistributions in binary form must reproduce
    the above copyright notice, this list of 
    conditions and the following disclaimer in the
    documentation and/or other materials provided
    with the distribution.
 3. Neither the name of the Contrail consortium nor the
    names of its contributors may be used to endorse
    or promote products derived from this software 
    without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, 
BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR 
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS 
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

Created February, 2012

@author mrlarkin

'''

from threading import Thread

from conpaas.core.expose import expose
from conpaas.core.manager import BaseManager, ManagerException
from conpaas.core.https.server import HttpJsonResponse, HttpErrorResponse, \
                                      HttpError
from conpaas.services.mapreduce.agent import client

class MapReduceManager(BaseManager):

    # Manager states - Used by the frontend
    S_INIT = 'INIT'         # manager initialized but not yet started
    S_PROLOGUE = 'PROLOGUE' # manager is initializing
    S_RUNNING = 'RUNNING'   # manager is running
    S_ADAPTING = 'ADAPTING' # manager is in a transient state - frontend will keep
                            # polling until manager out of transient state
    S_EPILOGUE = 'EPILOGUE' # manager is shutting down
    S_STOPPED = 'STOPPED'   # manager stopped
    S_ERROR = 'ERROR'       # manager is in error state

    def __init__(self,
                 config_parser, # config file
                 **kwargs):     # anything you can't send in config_parser
                                # (hopefully the new service won't need anything extra)
        BaseManager.__init__(self, config_parser)

        self.state = self.S_INIT
        self.nodes = []
        # Setup the clouds' controller
        self.controller.generate_context('mapreduce')
        clouds = self.controller.get_clouds()
        self.controller.config_cloud(clouds[0], { "mem" : "1024", "cpu" : "1" })

    @expose('POST')
    def startup(self, kwargs):
        ''' Starts the service - it will start and configure the scalaris management server  '''

        self.logger.debug("Entering HadoopManager startup")
        if len(kwargs) != 0:
            return HttpErrorResponse(ManagerException \
                                      (ManagerException.E_ARGS_UNEXPECTED, \
                                       kwargs.keys()).message)

        if self.state != self.S_INIT and self.state != self.S_STOPPED:
            return HttpErrorResponse(ManagerException(ManagerException.E_STATE_ERROR).message)
        self.state = self.S_PROLOGUE
        Thread(target=self._do_startup, args=[]).start()
        return HttpJsonResponse({'state': self.S_PROLOGUE})

    def _do_startup(self):
        ''' Starts up the service. The first node will be the job 
            master as well as an hadoop worker.
        '''
        try:
          self.context = {'FIRST': 'true',
                          'MGMT_SERVER': ''}
          self.controller.update_context(self.context)
          instance = self.controller.create_nodes(1, \
            client.check_agent_process, 5555)
          self.nodes += instance

          self.logger.info('Created node: %s', instance[0])
          client.startup(instance[0].ip, 5555,
                         instance[0].ip,
                         instance[0].private_ip)
          self.logger.info('Called startup: %s', instance[0])
          self.context = {'FIRST': 'false',
                          'MGMT_SERVER': instance[0].ip}
          self.controller.update_context(self.context)
        except:
          self.logger.exception('do_startup: Failed to request a new node')
          self.state = self.S_STOPPED
          return
        self.state = self.S_RUNNING

    @expose('POST')
    def shutdown(self, kwargs):
        self.state = self.S_EPILOGUE
        Thread(target=self._do_shutdown, args=[]).start()
        return HttpJsonResponse()

    def _do_shutdown(self):
      self.controller.delete_nodes(self.nodes)
      self.nodes = []
      self.state = self.S_STOPPED
      return HttpJsonResponse()

    @expose('POST')
    def add_nodes(self, kwargs):
        if self.state != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to add_nodes')
        if not 'workers' in kwargs:
            return HttpErrorResponse('ERROR: Required argument doesn\'t exist')
        if not isinstance(kwargs['workers'], int):
            return HttpErrorResponse('ERROR: Expected an integer value for "count"')
        count = int(kwargs.pop('workers'))
        # create at least one node
        if count < 1:
            return HttpErrorResponse('ERROR: Expected a positive integer value for "count"')
        self.state = self.S_ADAPTING
        Thread(target=self._do_add_nodes, args=[count]).start()
        return HttpJsonResponse()

    def _do_add_nodes(self, count):
        try:
            self.logger.info('Starting nodes: %d', count)
            node_instances = self.controller.create_nodes(count, \
                                client.check_agent_process, 5555)
            self.logger.info('Create nodes: %s', node_instances)
            self.nodes += node_instances
            # Startup agents
            for node in node_instances:
                client.startup(node.ip, 5555, node.ip, node.private_ip)
            self.logger.info('Started nodes: %d %s', count, self.state)
            return HttpJsonResponse()
        except HttpError as e:
            self.logger.info('exception in _do_add_nodes2: %s', e)
            return HttpJsonResponse()
        except Exception as e:
            self.logger.info('exception in _do_add_nodes1: %s', e)
            return HttpJsonResponse()
        finally:
            #TODO error handling (propagte error to client, i.e. browser)
            self.state = self.S_RUNNING
            self.logger.info('finished _do_add_nodes')
            return HttpJsonResponse()

    @expose('GET')
    def list_nodes(self, kwargs):
        self.logger.info('called list_nodes')
        if len(kwargs) != 0:
            return HttpErrorResponse('ERROR: Arguments unexpected')
        if self.state != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to list_nodes')
        return HttpJsonResponse({
          'masters' : [self.nodes[0].id],
          'workers': [ node.id for node in self.nodes[1:] ]
              })

    @expose('GET')
    def get_service_info(self, kwargs):
        self.logger.info('called get_service_info: %s', self.state)
        if len(kwargs) != 0:
            return HttpErrorResponse('ERROR: Arguments unexpected')
        return HttpJsonResponse({'state': self.state, 'type': 'mapreduce'})

    @expose('GET')
    def get_node_info(self, kwargs):
        self.logger.info('called get_node_info')
        if 'serviceNodeId' not in kwargs:
            return HttpErrorResponse('ERROR: Missing arguments')
        serviceNodeId = kwargs.pop('serviceNodeId')
        if len(kwargs) != 0:
            return HttpErrorResponse('ERROR: Arguments unexpected')
        serviceNode = None
        for node in self.nodes:
            if serviceNodeId == node.id:
                serviceNode = node
                break
        if serviceNode is None:
            return HttpErrorResponse('ERROR: Invalid arguments')
        return HttpJsonResponse({
            'serviceNode': {
                            'id': serviceNode.id,
                            'ip': serviceNode.ip
                            }
            })

    @expose('POST')
    def remove_nodes(self, kwargs):
        self.logger.info('called remove_nodes')
        if self.state != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to remove_nodes')
        if not 'workers' in kwargs:
            return HttpErrorResponse('ERROR: Required argument doesn\'t exist')
        if not isinstance(kwargs['workers'], int):
            return HttpErrorResponse('ERROR: Expected an integer value for "count"')
        count = int(kwargs.pop('workers'))
        self.state = self.S_ADAPTING
        Thread(target=self._do_remove_nodes, args=[count]).start()
        return HttpJsonResponse()

    def _do_remove_nodes(self, count):
        if count > len(self.nodes) - 1:
            self.state = self.S_RUNNING
            return HttpErrorResponse('ERROR: Cannot delete so many workers')
        for i in range(0, count):
            self.controller.delete_nodes([self.nodes.pop(1)])
        self.state = self.S_RUNNING
        return HttpJsonResponse()
