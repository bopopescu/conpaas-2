from threading import Thread

from conpaas.core.expose import expose
from conpaas.core.manager import BaseManager

from conpaas.core.https.server import HttpJsonResponse, HttpErrorResponse

from conpaas.services.helloworld.agent import client

class HelloWorldManager(BaseManager):

    # Manager states - Used by the Director
    S_INIT = 'INIT'         # manager initialized but not yet started
    S_PROLOGUE = 'PROLOGUE' # manager is starting up
    S_RUNNING = 'RUNNING'   # manager is running
    S_ADAPTING = 'ADAPTING' # manager is in a transient state - frontend will keep
                            # polling until manager out of transient state
    S_EPILOGUE = 'EPILOGUE' # manager is shutting down
    S_STOPPED = 'STOPPED'   # manager stopped
    S_ERROR = 'ERROR'       # manager is in error state

    AGENT_PORT = 5555

    def __init__(self, config_parser, **kwargs):
        BaseManager.__init__(self, config_parser)
        self.nodes = []
        # Setup the clouds' controller
        # self.controller.generate_context('helloworld')
        self.state = self.S_INIT

    def _do_startup(self, nodes):
        self.logger.info('nodes: %s' % nodes)
        
        # startCloud = self._init_cloud(cloud)

        # self.controller.add_context_replacement(dict(STRING='helloworld'))

        try:
            # nodes = self.controller.create_nodes(1,
            #     client.check_agent_process, self.AGENT_PORT, startCloud)

            node = nodes[0]

            client.startup(node.ip, self.AGENT_PORT)

            # Extend the nodes list with the newly created one
            self.nodes += nodes
            self.state = self.S_RUNNING
        except Exception, err:
            self.logger.exception('_do_startup: Failed to create node: %s' % err)
            self.state = self.S_ERROR


    # @expose('POST')
    # def shutdown(self, kwargs):
    #     self.state = self.S_EPILOGUE
    #     Thread(target=self._do_shutdown, args=[]).start()
    #     return HttpJsonResponse()

    # def _do_shutdown(self):
    #     self.controller.delete_nodes(self.nodes)
    #     self.nodes = []
    #     self.state = self.S_STOPPED
    

    def _do_stop(self):
        self.controller.delete_nodes(self.nodes)
        self.nodes = []
        self.state = self.S_STOPPED

    def get_service_type(self):
        return 'helloworld'

    def get_context_replacement(self):
        return dict(STRING='helloworld')

    # @expose('POST')
    # def add_nodes(self, kwargs):
    #     if self.state != self.S_RUNNING:
    #         return HttpErrorResponse('ERROR: Wrong state to add_nodes')

    #     if 'node' in kwargs:
    #         kwargs['count'] = kwargs['node']

    #     if not 'count' in kwargs:
    #         return HttpErrorResponse("ERROR: Required argument doesn't exist")

    #     if not isinstance(kwargs['count'], int):
    #         return HttpErrorResponse('ERROR: Expected an integer value for "count"')

    #     count = int(kwargs['count'])

    #     cloud = kwargs.pop('cloud', 'iaas')
    #     try:
    #         cloud = self._init_cloud(cloud)
    #     except Exception as ex:
    #             return HttpErrorResponse(
    #                 "A cloud named '%s' could not be found" % cloud)

    #     self.state = self.S_ADAPTING
    #     Thread(target=self._do_add_nodes, args=[count, cloud]).start()
    #     return HttpJsonResponse()

    # def _do_add_nodes(self, count, cloud):
    #     node_instances = self.controller.create_nodes(count,
    #             client.check_agent_process, self.AGENT_PORT, cloud)

    #     self.nodes += node_instances
    #     # Startup agents
    #     for node in node_instances:
    #         client.startup(node.ip, self.AGENT_PORT)

    #     self.state = self.S_RUNNING
    #     return HttpJsonResponse()

    # @expose('POST')
    # def remove_nodes(self, kwargs):
    #     if self.state != self.S_RUNNING:
    #         return HttpErrorResponse('ERROR: Wrong state to remove_nodes')

    #     if 'node' in kwargs:
    #         kwargs['count'] = kwargs['node']

    #     if not 'count' in kwargs:
    #         return HttpErrorResponse("ERROR: Required argument doesn't exist")

    #     if not isinstance(kwargs['count'], int):
    #         return HttpErrorResponse('ERROR: Expected an integer value for "count"')

    #     count = int(kwargs['count'])
    #     self.state = self.S_ADAPTING
    #     Thread(target=self._do_remove_nodes, args=[count]).start()
    #     return HttpJsonResponse()

    # def _do_remove_nodes(self, count):
    #     for _ in range(0, count):
    #         self.controller.delete_nodes([ self.nodes.pop() ])

    #     self.state = self.S_RUNNING
    #     return HttpJsonResponse()

    def add_nodes(self, nodes):
        self.nodes += nodes
        for node in nodes:
            client.startup(node.ip, self.AGENT_PORT)
        self.state = self.S_RUNNING

    def remove_nodes(self, nodes):
        # (genc): for the moment i am supposing only the number is passed and not the roles
        del_nodes = []
        for _ in range(0, nodes):
            del_nodes += [ self.nodes.pop() ]
        return del_nodes


    @expose('GET')
    def list_nodes(self, kwargs):
        if len(kwargs) != 0:
            return HttpErrorResponse('ERROR: Arguments unexpected')

        if self.state != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to list_nodes')

        return HttpJsonResponse({
              'helloworld': [ node.id for node in self.nodes ],
              })

    @expose('GET')
    def get_service_info(self, kwargs):
        if len(kwargs) != 0:
            return HttpErrorResponse('ERROR: Arguments unexpected')

        return HttpJsonResponse({'state': self.state, 'type': 'helloworld'})

    @expose('GET')
    def get_node_info(self, kwargs):
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

    

    @expose('GET')
    def get_helloworld(self, kwargs):
        if self.state != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to get_helloworld')

        messages = []

        # Just get_helloworld from all the agents
        for node in self.nodes:
            data = client.get_helloworld(node.ip, self.AGENT_PORT)
            message = 'Received %s from %s' % (data['result'], node.id)
            self.logger.info(message)
            messages.append(message)

        return HttpJsonResponse({ 'helloworld': "\n".join(messages) })
