# -*- coding: utf-8 -*-

"""
    :copyright: (C) 2010-2013 by Contrail Consortium.
"""

from threading import Thread

from conpaas.core.expose import expose

from conpaas.core.manager import BaseManager
from conpaas.core.manager import ManagerException

from conpaas.core.https.server import HttpJsonResponse, HttpErrorResponse
from conpaas.core.misc import run_cmd

from conpaas.services.xtreemfs.agent import client

import uuid
import base64
import subprocess
import tempfile

def invalid_arg(msg):
    return HttpErrorResponse(ManagerException(
        ManagerException.E_ARGS_INVALID, detail=msg).message)

class XtreemFSManager(BaseManager):
    
    def __init__(self, config_parser, **kwargs):
        BaseManager.__init__(self, config_parser)

        # node lists
        self.nodes = []    # all nodes         
        self.osdNodes = [] # only the OSD nodes  
        self.mrcNodes = [] # only the MRC nodes
        self.dirNodes = [] # only the DIR nodes   

        # node counters
        self.dirCount = 0
        self.mrcCount = 0
        self.osdCount = 0

        # wether we want to keep storage volumes upon OSD nodes deletion
        self.persistent = False

        # default value for OSD volume size
        self.osd_volume_size = 1024

        # dictionaries mapping node IDs to uuids
        self.dir_node_uuid_map = {}
        self.mrc_node_uuid_map = {}
        self.osd_node_uuid_map = {}
        
        # dictionary mapping osd uuids to volume IDs
        self.osd_uuid_volume_map = {}

        # Setup the clouds' controller
        # self.controller.generate_context('xtreemfs')
        
        # filename of the client certificate
        self.client_cert_filename = self.config_parser.get('manager', 'CERT_DIR') + "/client.p12"
        self.client_cert_passphrase = "asdf1234"

    def get_service_type(self):
        return 'xtreemfs'

    def get_starting_nodes(self):
        device_name=self.config_parser.get('manager', 'DEV_TARGET')
        volume = {'vol_name':'osd-%(vm_id)s', 'vol_size': self.osd_volume_size, 'dev_name':device_name}
        nodes = [{'cloud':None, 'volumes':[volume]}]
        return nodes

    def get_add_nodes_info(self, noderoles, cloud):
        device_name=self.config_parser.get('manager', 'DEV_TARGET')
        count = sum(noderoles.values())
        nodes_info = [{'cloud':cloud} for _ in range(count)]
        osd_nodes = noderoles.get('osd', 0)
        for node_info in nodes_info:
            if osd_nodes:
                volume = {'vol_name':'osd-%(vm_id)s', 'vol_size': self.osd_volume_size, 'dev_name':device_name}
                node_info['volumes'] = [volume]
                osd_nodes -= 1

        return nodes_info

    def __get__uuid(self, node_id, node_type):
        if node_type == 'dir':
            node_map = self.dir_node_uuid_map
        elif node_type == 'mrc':
            node_map = self.mrc_node_uuid_map
        elif node_type == 'osd':
            node_map = self.osd_node_uuid_map
        else:
            raise Exception("Unknown node type: %s" % node_type)
        
        node_uuid = node_map.get(node_id)

        if node_uuid:
            self.logger.debug("%s already has a uuid (%s) -> %s" % (node_id,
                node_type, node_uuid))
        else:
            node_uuid = str(uuid.uuid1())
            node_map[node_id] = node_uuid
            self.logger.debug("New uuid for %s (%s) -> %s" % (node_id,
                node_type, node_uuid))
            
        return node_uuid

    def _create_certs(self, nodes):
        for node in nodes:
            certs = {}
            # create a temporary directory
            tmpdir = tempfile.mkdtemp()
            # create certificates and truststore
            creation_cmd  = "bash "
            creation_cmd += self.config_parser.get('manager', 'CONPAAS_HOME')
            creation_cmd += "/src/conpaas/services/xtreemfs/etc/"
            creation_cmd += "generate_certificate.sh -dmo -t"
            out, err = run_cmd(creation_cmd, tmpdir)
            self.logger.debug('_create_certs: stderr %s' % out)
            self.logger.debug('_create_certs: stdout %s' % err)
            # store result as base64 encoded string into dictionary for transfer
            certs['dir'] = base64.b64encode(open(tmpdir + "/dir.p12", 'rb').read())
            certs['mrc'] = base64.b64encode(open(tmpdir + "/mrc.p12", 'rb').read())
            certs['osd'] = base64.b64encode(open(tmpdir + "/osd.p12", 'rb').read())
            certs['truststore'] = base64.b64encode(open(tmpdir + "/trusted.jks", 'rb').read())
            # transfer data to agent node
            client.set_certificates(node.ip, 5555, certs)

    def _create_client_cert(self, passphrase, adminflag):
        # create a temporary directory
        self.logger.debug('_create_client_cert: creating tmp dir')
        tmpdir = tempfile.mkdtemp()
        self.logger.debug('_create_client_cert: created tmp dir')
        # create certificates and truststore
        creation_cmd  = "bash "
        creation_cmd += self.config_parser.get('manager', 'CONPAAS_HOME')
        creation_cmd += "/src/conpaas/services/xtreemfs/etc/"
        creation_cmd += "generate_certificate.sh -c -p " + passphrase
        if adminflag:
            creation_cmd += " -s"
        self.logger.debug('_create_client_cert: executing script')
        out, err = run_cmd(creation_cmd, tmpdir)
        self.logger.debug('_create_client_cert: stderr %s' % out)
        self.logger.debug('_create_client_cert: stdout %s' % err)
        # store result as base64 encoded string into dictionary for transfer
        return open(tmpdir + "/client.p12", 'rb').read()

    def _create_user_cert(self, user, group, passphrase, adminflag):
        # create a temporary directory
        self.logger.debug('_create_user_cert: creating tmp dir')
        tmpdir = tempfile.mkdtemp()
        self.logger.debug('_create_user_cert: created tmp dir')
        # create certificates and truststore
        creation_cmd  = "bash "
        creation_cmd += self.config_parser.get('manager', 'CONPAAS_HOME')
        creation_cmd += "/src/conpaas/services/xtreemfs/etc/"
        creation_cmd += "generate_certificate.sh -u " + user + " -g " + group + " -p " + passphrase
        if adminflag:
            creation_cmd += " -s"
        self.logger.debug('_create_user_cert: executing script')
        out, err = run_cmd(creation_cmd, tmpdir)
        self.logger.debug('_create_user_cert: stderr %s' % out)
        self.logger.debug('_create_user_cert: stdout %s' % err)
        # store result as base64 encoded string into dictionary for transfer
        return open(tmpdir + "/" + user + ".p12", 'rb').read()

    def _start_dir(self, nodes):
        self.logger.debug("_start_dir(%s)" % nodes)

        for node in nodes:
            try:
                dir_uuid = self.__get__uuid(node.id, 'dir')
                client.createDIR(node.ip, 5555, dir_uuid)
            except client.AgentException:
                self.logger.exception('Failed to start DIR at node %s' % node)
                self.state_set(self.S_ERROR)
                raise

    def _stop_dir(self, nodes, remove):
        for node in nodes:
            try:
                client.stopDIR(node.ip, 5555)
            except client.AgentException:
                self.logger.exception('Failed to stop DIR at node %s' % node)
                self.state_set(self.S_ERROR)
                raise
            if remove:
                del self.dir_node_uuid_map[node.id]

    def _start_mrc(self, nodes):
        for node in nodes:
            try:
                mrc_uuid = self.__get__uuid(node.id, 'mrc')
                client.createMRC(node.ip, 5555, self.dirNodes[0].ip, mrc_uuid)
            except client.AgentException:
                self.logger.exception('Failed to start MRC at node %s' % node)
                self.state_set(self.S_ERROR)
                raise

    def _stop_mrc(self, nodes, remove):
        for node in nodes:
            try:
                client.stopMRC(node.ip, 5555)
            except client.AgentException:
                self.logger.exception('Failed to stop MRC at node %s' % node)
                self.state_set(self.S_ERROR)
                raise
            if remove:
                del self.mrc_node_uuid_map[node.id]

    def _start_osd(self, nodes):
        dev_name = None
        for idx, node in enumerate(nodes):
            volume_associated = False
            osd_uuid = self.__get__uuid(node.id, 'osd')
            # osd_uuid = node.volumes[0].vol_name
            self.osd_uuid_volume_map[osd_uuid] = node.volumes[0].vol_id
            dev_name = node.volumes[0].dev_name
            try:
                client.createOSD(node.ip, 5555, self.dirNodes[0].ip, osd_uuid,
                        mkfs=not volume_associated, device_name=dev_name)
            except client.AgentException:
                self.logger.exception('Failed to start OSD at node %s' % node)
                self.state_set(self.S_ERROR)
                raise

    # def _start_osd(self, nodes, cloud=None):
    #     dev_name = None
    #     for idx, node in enumerate(nodes):
    #         osd_uuid = self.__get__uuid(node.id, 'osd')

    #         volume_associated = osd_uuid in self.osd_uuid_volume_map

    #         # We need a storage volume for each OSD node. Check if this OSD
    #         # node needs a new volume to be created.
    #         if volume_associated:
    #             # No need to create a new volume.
    #             volume = self.get_volume(self.osd_uuid_volume_map[osd_uuid])

    #             self.logger.debug(
    #                 '%s already has an associated storage volume (%s)' %
    #                     (osd_uuid, volume.id))
    #         else:
    #             # We need to create a new volume.
    #             volume_name = "osd-%s" % osd_uuid
    #             volume = self.create_volume(self.osd_volume_size, volume_name,
    #                     node.vmid, cloud)
    #             self.osd_uuid_volume_map[osd_uuid] = volume.id

    #         try:
    #             _, dev_name = self.attach_volume(volume.id, node.vmid)
    #         except Exception, err:
    #             self.logger.error("attach_volume: %s" % err)

    #         try:
    #             client.createOSD(node.ip, 5555, self.dirNodes[0].ip, osd_uuid,
    #                     mkfs=not volume_associated, device_name=dev_name)
    #         except client.AgentException:
    #             self.logger.exception('Failed to start OSD at node %s' % node)
    #             self.state_set(self.S_ERROR)
    #             raise

    def _stop_osd(self, nodes, remove, drain):
        """Stop OSD service on the given nodes.
        
        The volume is always detached.
        
        If remove is True, the volume is destroyed and node and volume are 
        deleted from internal data structures.
        
        If drain is True, data is moved to other OSDs."""

        for node in nodes:
            try:
                client.stopOSD(node.ip, 5555, drain)
            except client.AgentException:
                self.logger.exception('Failed to stop OSD at node %s' % node)
                self.state_set(self.S_ERROR)
                raise

            # volume_id = self.osd_uuid_volume_map[self.osd_node_uuid_map[node.id]]
            # self.detach_volume(volume_id)

            # # destroy volumes and delete entries from internal state 
            # if remove:
            #     self.destroy_volume(volume_id)
            #     del self.osd_uuid_volume_map[self.osd_node_uuid_map[node.id]]
            #     del self.osd_node_uuid_map[node.id]
            # else:
            #     self.logger.debug('Not destroying volume %s' % volume_id)


    def on_start(self, nodes, resuming=False):
        # use this node for DIR, MRC and OSD
        # self.nodes += node_instances
        self.dirNodes += nodes
        self.mrcNodes += nodes
        self.osdNodes += nodes

        if not resuming:
            # create certificates for DIR, MRC, OSD and copy them to the agent 
            self._create_certs(nodes)
            # create a client certificate used by the manager to invoke xtreemfs operations
            open(self.client_cert_filename, 'wb').write(self._create_client_cert(self.client_cert_passphrase, True))
        
        # start DIR, MRC, OSD
        if not resuming:
            self._start_dir(self.dirNodes)
            self._start_mrc(self.mrcNodes)
            self._start_osd(self.osdNodes)

        # at the startup the DIR node will have all the services
        self.dirCount = 1
        self.mrcCount = 1
        self.osdCount = 1

        self.logger.info('Created 1 node with DIR, MRC and OSD services')
        self.logger.info('XtreemFS service was started up')
        return True

    # def _do_startup(self, cloud, resuming=False):
    #     """Starts up the service. The first nodes will contain all services. 
        
    #     If 'resuming' is set to True, we do not start XtreemFS services now.
    #     set_service_snapshot will do that.
    #     """
    #     startCloud = self._init_cloud(cloud)
    #     try:
    #         # NOTE: The following service structure is enforce:
    #         #       - the first node contains a DIR, MRC and OSD,
    #         #         those services can not be removed
    #         #       - added DIR, MRC and OSD services will all run
    #         #         on exclusive nodes
    #         #       - all explicitly added services can be removed

    #         # create 1 node
    #         node_instances = self.controller.create_nodes(1,
    #             client.check_agent_process, 5555, startCloud)
          
    #         # use this node for DIR, MRC and OSD
    #         self.nodes += node_instances
    #         self.dirNodes += node_instances
    #         self.mrcNodes += node_instances
    #         self.osdNodes += node_instances

    #         if not resuming:
    #             # create certificates for DIR, MRC, OSD and copy them to the agent 
    #             self._create_certs(node_instances)
    #             # create a client certificate used by the manager to invoke xtreemfs operations
    #             open(self.client_cert_filename, 'wb').write(self._create_client_cert(self.client_cert_passphrase, True))
            
    #         # start DIR, MRC, OSD
    #         if not resuming:
    #             self._start_dir(self.dirNodes)
    #             self._start_mrc(self.mrcNodes)
    #             self._start_osd(self.osdNodes, startCloud)

    #         # at the startup the DIR node will have all the services
    #         self.dirCount = 1
    #         self.mrcCount = 1
    #         self.osdCount = 1

    #         self.logger.info('Created 1 node with DIR, MRC and OSD services')
    #     except:
    #         self.controller.delete_nodes(node_instances)
    #         self.logger.exception('do_startup: Failed to request a new node')
    #         self.state_set(self.S_STOPPED)
    #         return

    #     self.logger.info('XtreemFS service was started up')    
    #     self.state_set(self.S_RUNNING)

    def _start_all(self):
        self._start_dir(self.dirNodes)
        self._start_mrc(self.mrcNodes)
        self._start_osd(self.osdNodes)

    def _stop_all(self, remove=True):
        """Stop all xtreemfs services on all agents (first osd, then mrc, then
        dir)."""
        # do not drain (move data to other OSDs), since we stop all
        self._stop_osd(self.osdNodes, remove=remove, drain=False) 
        self._stop_mrc(self.mrcNodes, remove=remove)
        self._stop_dir(self.dirNodes, remove=remove)

    def on_stop(self, stop_services=True):
        # check if we need to stop the services or not, i.e. when called at 
        # the end of get_snapshot()
        if stop_services:
            self._stop_all(remove=True)

        all_nodes = self.nodes[:]
        self.nodes = []
        self.dirNodes = []          
        self.mrcNodes = []
        self.osdNodes = []   
    
        self.dirCount = 0
        self.mrcCount = 0
        self.osdCount = 0

        self.dir_node_uuid_map = {}
        self.mrc_node_uuid_map = {}
        self.osd_node_uuid_map = {}

        self.osd_uuid_volume_map = {}

        return all_nodes


    # def _do_stop(self, stop_services=True):
    #     # check if we need to stop the services or not, i.e. when called at 
    #     # the end of get_snapshot()
    #     if stop_services:
    #         self._stop_all(remove=True)

    #     self.controller.delete_nodes(self.nodes)
    #     self.nodes = []
    #     self.dirNodes = []          
    #     self.mrcNodes = []
    #     self.osdNodes = []   
    
    #     self.dirCount = 0
    #     self.mrcCount = 0
    #     self.osdCount = 0

    #     self.dir_node_uuid_map = {}
    #     self.mrc_node_uuid_map = {}
    #     self.osd_node_uuid_map = {}

    #     self.osd_uuid_volume_map = {}

    #     self.state_set(self.S_STOPPED)
    #     return HttpJsonResponse()


    def on_add_nodes(self, nodes):
        # (genc): should manage the param checking somehow
        resuming = False;
        # if 'resuming' in kwargs:
        #     resuming = kwargs['resuming']
        
        
        # # Adding DIR Nodes
        # if 'dir' in kwargs:
        #     if not isinstance(kwargs['dir'], int):
        #         return invalid_arg('Expected an integer value for "dir"')
        #     nr_dir = int(kwargs.pop('dir'))    
        #     if nr_dir < 0: 
        #         return invalid_arg('Expected a positive integer value for "dir"')

        # # Adding MRC Nodes
        # if 'mrc' in kwargs:
        #     if not isinstance(kwargs['mrc'], int):
        #         return invalid_arg('Expected an integer value for "mrc"')
        #     nr_mrc = int(kwargs.pop('mrc'))
        #     if nr_mrc < 0: 
        #         return invalid_arg('Expected a positive integer value for "mrc"')

        # # TODO: 'osd' is no longer required, when adding other services is supported
        # if not 'osd' in kwargs:
        #     return HttpErrorResponse('ERROR: Required argument doesn\'t exist')
        # if not isinstance(kwargs['osd'], int):
        #     return HttpErrorResponse('ERROR: Expected an integer value for "osd"')

        # nr_osd = int(kwargs.pop('osd'))
        # if nr_osd < 0: 
        #     return invalid_arg('Expected a positive integer value for "nr osd"')

        dirNodesAdded = filter(lambda n: n.role == 'dir', nodes)
        mrcNodesAdded = filter(lambda n: n.role == 'mrc', nodes)
        osdNodesAdded = filter(lambda n: n.role == 'osd', nodes)
        self.dirNodes += dirNodesAdded
        self.mrcNodes += mrcNodesAdded
        self.osdNodes += osdNodesAdded

        for node in nodes:
            client.startup(node.ip, 5555)
        
        if not resuming:
            # create certificates for DIR, MRC, OSD and copy them to the agent 
            self._create_certs(nodes)

        # Startup DIR agents
        for node in dirNodesAdded:
            data = client.createDIR(node.ip, 5555)
            self.logger.info('Received %s from %s', data, node.id)
            self.dirCount += 1

        # Startup MRC agents
        for node in mrcNodesAdded:
            data = client.createMRC(node.ip, 5555, self.dirNodes[0].ip)
            self.logger.info('Received %s from %s', data, node.id)
            self.mrcCount += 1

        # Startup OSD agents (if not resuming)
        if not resuming:
            self._start_osd(osdNodesAdded)
      
        self.osdCount += len(osdNodesAdded)
        return True


        

    # @expose('POST')
    # def add_nodes(self, kwargs):
    #     #self.controller.add_context_replacement(dict(STRING='xtreemfs'))
    #     if self.state_get() != self.S_RUNNING:
    #         return HttpErrorResponse('ERROR: Wrong state to add_nodes')

    #     nr_dir = 0
    #     nr_mrc = 0 
    #     nr_osd = 0
        
        

    #     self.state_set(self.S_ADAPTING)
    #     Thread(target=self._do_add_nodes, args=[nr_dir, nr_mrc, nr_osd, kwargs['cloud'], resuming]).start()
    #     return HttpJsonResponse()
    
    # # TODO: currently not used
    # def KillOsd(self, nodes):
    #     for node in nodes:
    #         client.stopOSD(node.ip, 5555)
    #         self.osdNodes.remove(node)

    # def _do_add_nodes(self, nr_dir, nr_mrc, nr_osd, cloud, resuming=False):
    #     startCloud = self._init_cloud(cloud)
    #     totalNodes = nr_dir + nr_mrc + nr_osd

    #     # try to create totalNodes new nodes
    #     try:
    #         node_instances = self.controller.create_nodes(totalNodes, 
    #             client.check_agent_process, 5555, startCloud)      
    #     except:
    #         self.logger.exception('_do_add_nodes: Failed to request a new node')
    #         self.state_set(self.S_STOPPED)
    #         return

    #     self.nodes += node_instances 

    #     dirNodesAdded = node_instances[:nr_dir]
    #     self.dirNodes += dirNodesAdded

    #     mrcNodesAdded = node_instances[nr_dir:nr_mrc+nr_dir]
    #     self.mrcNodes += mrcNodesAdded

    #     osdNodesAdded = node_instances[nr_mrc+nr_dir:] 
    #     self.osdNodes += osdNodesAdded

    #     # TODO: maybe re-enable when OSD-removal moves data to another node before shutting down the service.
    #     #KilledOsdNodes = []
    #     # The first node will contain the OSD service so it will be removed
    #     # from there
    #     #if nr_osd > 0 and self.osdCount == 0:
    #     #    KilledOsdNodes.append(self.dirNodes[0])
    #     #self.KillOsd(KilledOsdNodes)

    #     for node in node_instances:
    #         client.startup(node.ip, 5555)
        
    #     if not resuming:
    #         # create certificates for DIR, MRC, OSD and copy them to the agent 
    #         self._create_certs(node_instances)

    #     # Startup DIR agents
    #     for node in dirNodesAdded:
    #         data = client.createDIR(node.ip, 5555)
    #         self.logger.info('Received %s from %s', data, node.id)
    #         self.dirCount += 1

    #     # Startup MRC agents
    #     for node in mrcNodesAdded:
    #         data = client.createMRC(node.ip, 5555, self.dirNodes[0].ip)
    #         self.logger.info('Received %s from %s', data, node.id)
    #         self.mrcCount += 1

    #     # Startup OSD agents (if not resuming)
    #     if not resuming:
    #         self._start_osd(osdNodesAdded, startCloud)
      
    #     self.osdCount += len(osdNodesAdded)

    #     #for node in osdNodesAdded:
    #     #    client.startup(node.ip, 5555)
    #     #    data = client.createOSD(node.ip, 5555, self.dirNodes[0].ip)
    #     #    self.logger.info('Received %s from %s', data, node.id)         
    #     #    self.osdCount += 1

    #     self.state_set(self.S_RUNNING)
    #     return HttpJsonResponse()

    @expose('GET')
    def list_nodes(self, kwargs):
        if len(kwargs) != 0:
            return HttpErrorResponse('ERROR: Arguments unexpected')
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to list_nodes')
        return HttpJsonResponse({
              'dir': [node.id for node in self.dirNodes ],
              'mrc': [node.id for node in self.mrcNodes],
              'osd': [node.id for node in self.osdNodes]
              })

    @expose('GET')
    def get_service_info(self, kwargs):
        if len(kwargs) != 0:
            return HttpErrorResponse('ERROR: Arguments unexpected')
        return HttpJsonResponse({
            'state': self.state, 
            'type': 'xtreemfs',
            'persistent': self.persistent,
            'osd_volume_size': self.osd_volume_size
        })

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
            return HttpErrorResponse('ERROR: Unknown service node identifier "%s"' % serviceNodeId)
        return HttpJsonResponse({
            'serviceNode': {
                            'id': serviceNode.id,
                            'ip': serviceNode.ip,
                            'dir': serviceNode in self.dirNodes,
                            'mrc': serviceNode in self.mrcNodes,
                            'osd': serviceNode in self.osdNodes
                            }
            })


    def on_remove_nodes(self, noderoles):
        
        # (genc): again make a method to check these parameters    
        # # Removing DIR Nodes
        # if 'dir' in kwargs:
        #     if not isinstance(kwargs['dir'], int):
        #         return invalid_arg('Expected an integer value for "dir"')
        #     nr_dir = int(kwargs.pop('dir'))    
        #     if nr_dir < 0: 
        #         return invalid_arg('Expected a positive integer value for "dir"')
        #     if nr_dir > self.dirCount - 1: # we need at least 1 DIR
        #         return invalid_arg('Cannot remove_nodes that many DIR nodes')
     
        # # Removing MRC nodes
        # if 'mrc' in kwargs:
        #     if not isinstance(kwargs['mrc'], int):
        #         return invalid_arg('Expected an integer value for "mrc"')
        #     nr_mrc = int(kwargs.pop('mrc'))
        #     if nr_mrc < 0: 
        #         return invalid_arg('Expected a positive integer value for "mrc"')
        #     if nr_mrc > self.mrcCount - 1: # we need at least 1 MRC
        #         return invalid_arg('Cannot remove_nodes that many MRC nodes')

        # # TODO: 'osd' is no longer required, when removing other services is supported
        # if not 'osd' in kwargs:
        #     return HttpErrorResponse('ERROR: Required argument doesn\'t exist')
        # if not isinstance(kwargs['osd'], int):
        #     return HttpErrorResponse(
        #         'ERROR: Expected an integer value for "osd"')

        # nr_osd = int(kwargs.pop('osd'))
        # if nr_osd < 0: 
        #     return invalid_arg('Expected a positive integer value for "osd"')
        # if nr_osd > self.osdCount - 1: # we need at least 1 OSD
        #     return invalid_arg('Cannot remove_nodes that many OSD nodes')

        nr_dir = noderoles.get('dir', 0)
        nr_mrc = noderoles.get('mrc', 0)
        nr_osd = noderoles.get('osd', 0)

        self.logger.info('Removing %s dir, %s mrc and %s osd nodes' % (nr_dir, nr_mrc, nr_osd))
        rem_nodes = []
        if nr_dir > 0:
            for _ in range(0, nr_dir):
                node = self.dirNodes.pop(1)
                self._stop_dir([node], remove=True)
                rem_nodes += [node]
            self.dirCount -= nr_osd

        if nr_mrc > 0:
            for _ in range(0, nr_mrc):
                node = self.mrcNodes.pop(1)
                self._stop_mrc([node], remove=True)
                rem_nodes += [node]
            self.mrcCount -= nr_mrc

        if nr_osd > 0:
            for _ in range(0, nr_osd):
                node = self.osdNodes.pop(1)
                self._stop_osd([node], remove=True, drain=True)
                rem_nodes += [node]
            self.osdCount -= nr_osd

        self.logger.info('Nodes to remove: %s' % (rem_nodes))


        if len(self.osdNodes) + len(self.mrcNodes) + len(self.dirNodes) == 0:
            self.state_set(self.S_STOPPED)    
        else: 
            self.state_set(self.S_RUNNING)
        return rem_nodes


    @expose('POST')
    def remove_nodes(self, kwargs):
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to remove_nodes')

        nr_dir = 0
        nr_mrc = 0
        nr_osd = 0
            
        # Removing DIR Nodes
        if 'dir' in kwargs:
            if not isinstance(kwargs['dir'], int):
                return invalid_arg('Expected an integer value for "dir"')
            nr_dir = int(kwargs.pop('dir'))    
            if nr_dir < 0: 
                return invalid_arg('Expected a positive integer value for "dir"')
            if nr_dir > self.dirCount - 1: # we need at least 1 DIR
                return invalid_arg('Cannot remove_nodes that many DIR nodes')
     
        # Removing MRC nodes
        if 'mrc' in kwargs:
            if not isinstance(kwargs['mrc'], int):
                return invalid_arg('Expected an integer value for "mrc"')
            nr_mrc = int(kwargs.pop('mrc'))
            if nr_mrc < 0: 
                return invalid_arg('Expected a positive integer value for "mrc"')
            if nr_mrc > self.mrcCount - 1: # we need at least 1 MRC
                return invalid_arg('Cannot remove_nodes that many MRC nodes')

        # TODO: 'osd' is no longer required, when removing other services is supported
        if not 'osd' in kwargs:
            return HttpErrorResponse('ERROR: Required argument doesn\'t exist')
        if not isinstance(kwargs['osd'], int):
            return HttpErrorResponse(
                'ERROR: Expected an integer value for "osd"')

        nr_osd = int(kwargs.pop('osd'))
        if nr_osd < 0: 
            return invalid_arg('Expected a positive integer value for "osd"')
        if nr_osd > self.osdCount - 1: # we need at least 1 OSD
            return invalid_arg('Cannot remove_nodes that many OSD nodes')

        self.state_set(self.S_ADAPTING)
        Thread(target=self._do_remove_nodes, args=[nr_dir, nr_mrc, nr_osd]).start()
        return HttpJsonResponse()

    def _do_remove_nodes(self, nr_dir, nr_mrc, nr_osd):
        # NOTE: the logically unremovable first node which contains all
        #       services is ignored by using 1 instead of 0 in:
        #   for _ in range(0, nr_[dir|mrc|osd]):
        #        node = self.[dir|mrc|osd]Nodes.pop(1)

        if nr_dir > 0:
            for _ in range(0, nr_dir):
                node = self.dirNodes.pop(1)
                self._stop_dir([node], remove=True)
                self.controller.delete_nodes([node])
                self.nodes.remove(node)
            self.dirCount -= nr_osd

        if nr_mrc > 0:
            for _ in range(0, nr_mrc):
                node = self.mrcNodes.pop(1)
                self._stop_mrc([node], remove=True)
                self.controller.delete_nodes([node])
                self.nodes.remove(node)
            self.mrcCount -= nr_mrc

        if nr_osd > 0:
            for _ in range(0, nr_osd):
                node = self.osdNodes.pop(1)
                self._stop_osd([node], remove=True, drain=True)
                self.controller.delete_nodes([node])
                self.nodes.remove(node)
            self.osdCount -= nr_osd

        self.state_set(self.S_RUNNING)

        # TODO: maybe re-enable when OSD-removal moves data to another node before shutting down the service.
        # if there are no more OSD nodes we need to start OSD service on the
        # DIR node
        #if self.osdCount == 0:
        #    self.osdNodes.append(self.dirNodes[0])
        #    self._start_osd(self.dirNodes)

        return HttpJsonResponse()


    @expose('POST')
    def createMRC(self, kwargs):
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to create MRC service')
        # Just createMRC from all the agents
        for node in self.nodes:
            data = client.createMRC(node.ip, 5555, self.dirNodes[0].ip)
            self.logger.info('Received %s from %s', data, node.id)
        return HttpJsonResponse({
            'xtreemfs': [ node.id for node in self.nodes ],
            })   

    @expose('POST')
    def createDIR(self, kwargs):
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to create DIR service')
        # Just createDIR from all the agents
        for node in self.nodes:
            data = client.createDIR(node.ip, 5555)
            self.logger.info('Received %s from %s', data, node.id)
        return HttpJsonResponse({
            'xtreemfs': [ node.id for node in self.nodes ],
            })   

    @expose('POST')
    def createOSD(self, kwargs):
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to create OSD service')
        # Just createOSD from all the agents
        for node in self.nodes:
            data = client.createOSD(node.ip, 5555, self.dirNodes[0].ip)
            self.logger.info('Received %s from %s', data, node.id)
        return HttpJsonResponse({
            'xtreemfs': [ node.id for node in self.nodes ],
            }) 
    
    @expose('POST') 
    def createVolume(self, kwargs):
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to create Volume')

        if not 'volumeName' in kwargs:
            return HttpErrorResponse(
                'ERROR: Required argument (volumeName) doesn\'t exist')

        volumeName = kwargs.pop('volumeName')

        # Get the value of 'owner', if specified. 'xtreemfs' otherwise
        owner = kwargs.pop('owner', 'xtreemfs')

        args = [ 'mkfs.xtreemfs',
                 '%s:32636/%s' % (self.mrcNodes[0].ip, volumeName),
                 "-u", owner,
                 "-g", owner,
                 "-m", "777",
                 "--pkcs12-file-path", self.client_cert_filename,
                 "--pkcs12-passphrase", self.client_cert_passphrase ]

        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout, stderr) = process.communicate()
        process.poll()

        if process.returncode != 0:
            self.logger.info('Failed to create volume: %s; %s', stdout, stderr)
            return HttpErrorResponse("The volume could not be created")

        self.logger.info('Creating Volume: %s; %s', stdout, stderr)
        return HttpJsonResponse()

    @expose('POST') 
    def deleteVolume(self, kwargs):
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to delete Volume')

        if not 'volumeName' in kwargs:
            return HttpErrorResponse(
                'ERROR: Required argument (volumeName) doesn\'t exist')

        volumeName = kwargs.pop('volumeName')

        args = [ 'rmfs.xtreemfs',
                 '-f',
                 "--pkcs12-file-path", self.client_cert_filename,
                 "--pkcs12-passphrase", self.client_cert_passphrase,
                 '%s:32636/%s' % (self.mrcNodes[0].ip, volumeName) ]

        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout, stderr) = process.communicate()
        process.poll()

        if process.returncode != 0:
            self.logger.info('Failed to delete volume: %s; %s', stdout, stderr)
            return HttpErrorResponse("The volume could not be deleted")

        self.logger.info('Deleting Volume: %s; %s', stdout, stderr)
        # TODO(maybe): issue xtfs_cleanup on all OSDs to free space (or don't and assume xtfs_cleanup is run by a cron job or something)
        return HttpJsonResponse()

    @expose('GET')
    def listVolumes(self, kwargs):
        if len(kwargs) != 0:
            return HttpErrorResponse('ERROR: Arguments unexpetced')

        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to view volumes')

        args = [ 'lsfs.xtreemfs', 
                 "--pkcs12-file-path", self.client_cert_filename,
                 "--pkcs12-passphrase", self.client_cert_passphrase,
                 self.mrcNodes[0].ip + ':32636' ]

        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout, stderr) = process.communicate()
        process.poll()

        if process.returncode != 0:
            self.logger.info('Failed to view volume: %s; %s', stdout, stderr)
            return HttpErrorResponse("The volume list cannot be accessed")

        return HttpJsonResponse({ 'volumes': stdout })

    # NOTE: see xtfsutil for the available policies
    @expose('GET')
    def list_striping_policies(self, kwargs):
        if len(kwargs) != 0:
            return HttpErrorResponse('ERROR: Arguments unexpetced')
        return HttpJsonResponse({ 'policies': "RAID0" })

    @expose('GET')
    def list_replication_policies(self, kwargs):
        if len(kwargs) != 0:
            return HttpErrorResponse('ERROR: Arguments unexpetced')
        return HttpJsonResponse({ 'policies': "ronly, WaR1, WqRq" })

    @expose('GET')
    def list_osd_sel_policies(self, kwargs):
        if len(kwargs) != 0:
            return HttpErrorResponse('ERROR: Arguments unexpetced')
        return HttpJsonResponse({ 'policies': "DEFAULT, FQDN, UUID, DCMAP, VIVALDI" })

    @expose('GET')
    def list_replica_sel_policies(self, kwargs):
        if len(kwargs) != 0:
            return HttpErrorResponse('ERROR: Arguments unexpetced')
        return HttpJsonResponse({ 'policies': "DEFAULT, FQDN, DCMAP, VIVALDI" })

    def set_policy(self, volumeName, policyName, args):
        mountPoint = '/tmp/' + volumeName
        
        # mkdir -p <mountpoint>
        process = subprocess.Popen(['mkdir', '-p', mountPoint])
        (stdout, stderr) = process.communicate()
        process.poll()
        if process.returncode != 0:
            self.logger.info('Failed to set %s policy: %s; %s', policyName, stdout, stderr)
            return HttpErrorResponse("Failed to set %s policy: %s; %s" % (policyName, stdout, stderr))

        # mount.xtreemfs <dir_ip>:32638/<volumename> <mountpoint>
        process = subprocess.Popen(['mount.xtreemfs',
                                    "--pkcs12-file-path", self.client_cert_filename,
                                    "--pkcs12-passphrase", self.client_cert_passphrase,
                                    '%s:32638/%s' % (self.dirNodes[0].ip, volumeName),
                                    mountPoint],  
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout, stderr) = process.communicate()
        process.poll()
        if process.returncode != 0:
            self.logger.info('Failed to set %s policy: %s; %s', policyName, stdout, stderr)
            return HttpErrorResponse("Failed to set %s policy: %s; %s" % (policyName, stdout, stderr))

#        # with python 2.7
#        try: 
#            # mkdir -p <mountpoint>
#            subprocess.check_output(['mkdir', '-p', mountPoint])
#            # mount.xtreemfs <dir_ip>:32638/<volumename> <mountpoint>
#            subprocess.check_output(['mount.xtreemfs',
#                                     '%s:32638/%s' % (self.dirNodes[0].ip, volumeName),
#                                     mountPoint],  
#                                    stdout=subprocess.STDOUT)
#        except subprocess.CalledProcessError as e:
#            return HttpErrorResponse('ERROR: could not mount volume: ' + e.output)

        # xtfsutil <mountpoint> args
        process = subprocess.Popen(['xtfsutil', mountPoint] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout_xtfsutil, stderr_xtfsutil) = (stdout, stderr) = process.communicate()
        process.poll()

        if process.returncode != 0:
            self.logger.info('Failed to set %s policy: %s; %s', policyName, stdout, stderr)
            return HttpErrorResponse("Failed to set %s policy: %s; %s" % (policyName, stdout, stderr))

        # umount <mountpoint>
        process = subprocess.Popen(['umount', mountPoint],  
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout, stderr) = process.communicate()
        process.poll()
        if process.returncode != 0:
            self.logger.info('Failed to set %s policy: %s; %s', policyName, stdout, stderr)
            return HttpErrorResponse("Failed to set %s policy: %s; %s" % (policyName, stdout, stderr))

        # rmdir <mountpoint>
        process = subprocess.Popen(['rmdir', mountPoint])
        (stdout, stderr) = process.communicate()
        process.poll()
        if process.returncode != 0:
            self.logger.info('Failed to set %s policy: %s; %s', policyName, stdout, stderr)
            return HttpErrorResponse("Failed to set %s policy: %s; %s" % (policyName, stdout, stderr))

#        # with python 2.7
#        try: 
#            # umount <mountpoint>
#            subprocess.check_output(['umount', mountPoint])
#            # fusermount -u <mountpoint>
#            #subprocess.check_output(['fusermount', '-u', mountPoint])
#               # rmdir <mountpoint>
#            subprocess.check_output(['rmdir', mountPoint])
#        except subprocess.CalledProcessError as e:
#            return HttpErrorResponse('ERROR: could not unmount volume: ' + e.output)

        self.logger.info('Setting %s policy: %s; %s', policyName, stdout_xtfsutil, stderr_xtfsutil)
        return HttpJsonResponse({ 'stdout': stdout_xtfsutil })

    @expose('POST')
    def set_osd_sel_policy(self, kwargs):
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to set OSD selection policy.')

        if not 'volumeName' in kwargs:
            return HttpErrorResponse('ERROR: Required argument (volumeName) doesn\'t exist')
        if not 'policy' in kwargs:
            return HttpErrorResponse('ERROR: Required argument (policy) doesn\'t exist')

        volumeName = kwargs.pop('volumeName')
        policy = kwargs.pop('policy')

        # xtfsutil <path> --set-osp <policy>
        args = [ '--set-osp', policy ]
        
        return self.set_policy(volumeName, 'OSD selection', args)

    @expose('POST')
    def set_replica_sel_policy(self, kwargs):
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to set Replica selection policy.')

        if not 'volumeName' in kwargs:
            return HttpErrorResponse('ERROR: Required argument (volumeName) doesn\'t exist')
        if not 'policy' in kwargs:
            return HttpErrorResponse('ERROR: Required argument (policy) doesn\'t exist')

        volumeName = kwargs.pop('volumeName')
        policy = kwargs.pop('policy')

        # xtfsutil <path> --set-rsp <policy>
        args = [ '--set-rsp', policy ]
        
        return self.set_policy(volumeName, 'Replica selection', args)

    @expose('POST')
    def set_replication_policy(self, kwargs):
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to set Replication policy.')

        if not 'volumeName' in kwargs:
            return HttpErrorResponse('ERROR: Required argument (volumeName) doesn\'t exist')
        if not 'policy' in kwargs:
            return HttpErrorResponse('ERROR: Required argument (policy) doesn\'t exist')
        if not 'factor' in kwargs:
            return HttpErrorResponse('ERROR: Required argument (factor) doesn\'t exist')

        volumeName = kwargs.pop('volumeName')
        policy = kwargs.pop('policy')
        factor = kwargs.pop('factor')

        # xtfsutil <path> --set-drp --replication-policy <policy> --replication-factor <factor>
        args = [ '--set-drp',
                 '--replication-policy', policy,
                 '--replication-factor', factor ]
        
        return self.set_policy(volumeName, 'Replication', args)

    @expose('POST')
    def set_striping_policy(self, kwargs):
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to set Striping policy.')

        if not 'volumeName' in kwargs:
            return HttpErrorResponse('ERROR: Required argument (volumeName) doesn\'t exist')
        if not 'policy' in kwargs:
            return HttpErrorResponse('ERROR: Required argument (policy) doesn\'t exist')
        if not 'width' in kwargs:
            return HttpErrorResponse('ERROR: Required argument (factor) doesn\'t exist')
        if not 'stripe-size' in kwargs:
            return HttpErrorResponse('ERROR: Required argument (stripe-size) doesn\'t exist')


        volumeName = kwargs.pop('volumeName')
        policy = kwargs.pop('policy')
        width = kwargs.pop('width')
        stripe_size = kwargs.pop('stripe-size')

        # xtfsutil <path> --set-dsp --striping-policy <policy> --striping-policy-width <width> --striping-policy-stripe-size <stripe-size>
        args = [ '--set-dsp',
                 '--striping-policy', policy,
                 '--striping-policy-width', width,
                 '--striping-policy-stripe-size', stripe_size ]
        
        return self.set_policy(volumeName, 'Striping', args)

    @expose('POST')
    def toggle_persistent(self, kwargs):
        self.persistent = not self.persistent
        self.logger.debug('toggle_persistent: %s' % self.persistent)
        return self.get_service_info({})

    @expose('POST')
    def set_osd_size(self, kwargs):
        if not 'size' in kwargs:
            return HttpErrorResponse("ERROR: Required argument (size) doesn't exist")
        try:
            self.osd_volume_size = int(kwargs['size'])
            self.logger.debug('set_osd_size: %s' % self.osd_volume_size)
            return self.get_service_info({})
        except ValueError:
            return HttpErrorResponse("ERROR: Required argument (size) should be an integer")

    @expose('POST')
    def get_service_snapshot(self, kwargs):
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse(
                'ERROR: Wrong state to get service snapshot.')

        self.state_set(self.S_EPILOGUE)

        # stop all agent services        
        self.logger.debug("Stopping all agent services")
        self._stop_all(remove=False)

        self.logger.debug("Calling get_snapshot on agents")

        # dictionary mapping node IDs to tuples of uuids/None (DIR, MRC, OSD)
        nodes_snapshot = {}        

        for node in self.nodes:
            if node.id not in nodes_snapshot:
                nodes_snapshot[node.id] = { 
                        'data': None, 
                        'dir_uuid': self.dir_node_uuid_map.get(node.id),
                        'mrc_uuid': self.mrc_node_uuid_map.get(node.id),
                        'osd_uuid': self.osd_node_uuid_map.get(node.id)
                }

            try:
                # get snapshot from this agent node, independent of what
                # XtreemFS services are running there
                data = client.get_snapshot(node.ip, 5555)
                self.logger.debug('get_snapshot(%s) HTTP code: %s' % (node.ip,
                    data[0]))
                nodes_snapshot[node.id]['data'] = base64.b64encode(data[1])
            except client.AgentException:
                self.logger.exception('Failed to get snapshot from node %s' %
                        node)
                self.state_set(self.S_ERROR)
                raise

            # Get ID of attached volume
            volume_id = self.osd_uuid_volume_map.get(
                    nodes_snapshot[node.id]['osd_uuid'])
            nodes_snapshot[node.id]['volume'] = volume_id

            if volume_id:
                volume = self.get_volume(volume_id)
                nodes_snapshot[node.id]['cloud'] = volume.cloud.cloud_name
        
            for key in 'dir_uuid', 'mrc_uuid', 'osd_uuid', 'volume':
                self.logger.debug("nodes_snapshot[%s]['%s']: %s" % (node.id,
                    key, nodes_snapshot[node.id][key]))

        # manager data
        filename = "/root/snapshot.tar.gz"
        dirs = self.config_parser.get('manager', 'CERT_DIR')

        err, out = run_cmd("tar -czf %s %s" % (filename, dirs), "/")
        if err:
            self.logger.exception(err)
            return HttpErrorResponse(err)
        manager_data = base64.b64encode(open(filename, 'rb').read())
        
        self.logger.debug("Shutting all agents down")
        self._do_shutdown(stop_services=False)
        return HttpJsonResponse({'nodes' : nodes_snapshot.values(), 'manager' : manager_data})

    @expose('POST')
    def set_service_snapshot(self, kwargs):
        if self.state_get() != self.S_RUNNING:
            return HttpErrorResponse(
                'ERROR: Wrong state to set service snapshot.')

        if not 'manager' in kwargs:
            return HttpErrorResponse(
               "ERROR: Required argument (manager) doesn't exist")
        if not 'nodes' in kwargs:
            return HttpErrorResponse(
               "ERROR: Required argument (nodes) doesn't exist")

        nodes = kwargs['nodes']

        if len(nodes) != len(self.nodes):
            err = "set_service_snapshot: len(nodes) != len(self.nodes)"
            self.logger.error(err)
            return HttpErrorResponse(err)
                    
        self.logger.info("set_service_snapshot: stopping all agent services")

        # rewriting state
        self.osdNodes = []
        self.mrcNodes = []
        self.dirNodes = []

        self.dir_node_uuid_map = {}
        self.mrc_node_uuid_map = {}
        self.osd_node_uuid_map = {}

        self.osd_uuid_volume_map = {}

        for node, data in zip(self.nodes, nodes):
            volumeid = data.get('volume')
            osd_uuid = data.get('osd_uuid')
            mrc_uuid = data.get('mrc_uuid')
            dir_uuid = data.get('dir_uuid')

            # If this is a dir node
            if dir_uuid:
                self.dir_node_uuid_map[node.id] = dir_uuid
                self.dirNodes.append(node)

            # If this is a mrc node
            if mrc_uuid:
                self.mrc_node_uuid_map[node.id] = mrc_uuid
                self.mrcNodes.append(node)

            # If this is an OSD node
            if osd_uuid:
                self.osd_node_uuid_map[node.id] = osd_uuid
                self.osdNodes.append(node)

                if volumeid:
                    self.osd_uuid_volume_map[osd_uuid] = volumeid

                    try:
                        self.get_volume(volumeid)
                    except Exception:
                        # This volume is not in the list of known ones.
                        volumeCloud = self._init_cloud(data.get('cloud'))
                        class volume:
                            id = volumeid
                            cloud = volumeCloud

                        self.volumes.append(volume)

            # Regardless of node type, restore metadata
            try:
                self.logger.info('set_service_snapshot: restoring %s' %
                        node.ip)
                data = client.set_snapshot(node.ip, 5555, data['archive'])
            except client.AgentException, err:
                self.logger.exception(err)
                raise err

        # restore manager data
        manager_data = kwargs['manager']
        filename = "/root/manager_data.tar.gz"
        open(filename, 'wb').write(base64.b64decode(manager_data))
        
        err, out = run_cmd("tar -xzf %s" % filename, "/")
        if err:
            self.logger.exception(err)
            return HttpErrorResponse(err)

        self.logger.info("set_service_snapshot: starting all agent services")
        self._start_all()
        self.logger.info("set_service_snapshot: all agent services started")
        return HttpJsonResponse()
        

    @expose('POST')
    def get_user_cert(self, kwargs):
        if not 'user' in kwargs:
            return HttpErrorResponse("ERROR: Required argument (user) doesn't exist")
        if not 'group' in kwargs:
            return HttpErrorResponse("ERROR: Required argument (group) doesn't exist")
        if not 'passphrase' in kwargs:
            return HttpErrorResponse("ERROR: Required argument (passphrase) doesn't exist")
        if not 'adminflag' in kwargs:
            return HttpErrorResponse("ERROR: Required argument (adminflag) doesn't exist")
        cert = self._create_user_cert(kwargs['user'], kwargs['group'], 
                kwargs['passphrase'], kwargs['adminflag'])
        return HttpJsonResponse({'cert' : base64.b64encode(cert)}) 

    @expose('POST')
    def get_client_cert(self, kwargs):
        if not 'passphrase' in kwargs:
            return HttpErrorResponse("ERROR: Required argument (passphrase) doesn't exist")
        if not 'adminflag' in kwargs:
            return HttpErrorResponse("ERROR: Required argument (adminflag) doesn't exist")
        cert = self._create_client_cert(kwargs['passphrase'], kwargs['adminflag'])
        return HttpJsonResponse({'cert' : base64.b64encode(cert)}) 
