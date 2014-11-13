import sys
import os

from cps.base import BaseClient

# TODO: as this file was created from a BLUEPRINT file,
# 	you may want to change ports, paths and/or methods (e.g. for hub)
#	to meet your specific service/server needs

class Client(BaseClient):

    def info(self, service_id):
        service = BaseClient.info(self, service_id)
        
        nodes = self.callmanager(service['sid'], "list_nodes", False, {})
        if 'hub' in nodes and nodes['hub']:
            # Only one HUB
            hub = nodes['hub'][0]
            params = { 'serviceNodeId': hub }
            details = self.callmanager(service['sid'], "get_node_info", False, params)
            print "hub url: ", "http://%s:4444" % details['serviceNode']['ip']
            print "node url:", "http://%s:3306" % details['serviceNode']['ip']

        if 'node' in nodes:
            # Multiple nodes
            for node in nodes['node']:
                params = { 'serviceNodeId': node }
                details = self.callmanager(service['sid'], "get_node_info", False, params)
                print "node url:", "http://%s:3306" % details['serviceNode']['ip']

    def usage(self, cmdname):
        BaseClient.usage(self, cmdname)
        print "    add_nodes         serviceid count"
        print "    remove_nodes      serviceid count"
        print "    upload_code       serviceid filename  # upload a new code version"
        print "    list_uploads      serviceid           # list uploaded code versions"
        print "    enable_code       serviceid version   # set a specific code version active"
        print "    run               serviceid           # deploy the application"

    def main(self, argv):
        command = argv[1]
   
        if command in ( 'add_nodes', 'remove_nodes', 'upload_code', 'list_uploads', 'enable_code', 'run' ): 
            try:                                                      
                sid = int(argv[2])                                    
            except (IndexError, ValueError):                          
                self.usage(argv[0])                                   
                sys.exit(0)                                           
                                                              
            self.check_service_id(sid)                                

  
        if command in ( 'add_nodes', 'remove_nodes'):
            try:
                count = int(argv[3])
            except (IndexError, ValueError):
                self.usage(argv[0])
                sys.exit(0)

            # call the method
            res = self.callmanager(sid, command, True, { 'count': count })
            if 'error' in res:
                print res['error']
            else:
                print "Service", sid, "is performing the requested operation (%s)" % command

        if command == 'upload_code':
            try: 
                filename = argv[3]
                if not (os.path.isfile(filename) and os.access(filename, os.R_OK)):
                    raise IndexError                                               
            except IndexError:                                                     
                self.usage(argv[0])                                                
                sys.exit(0)                                                        
                                                                       
            getattr(self, command)(sid, filename)                    
        
        if command == 'run':            
            getattr(self, command)(sid)                    
    
        if command == 'list_uploads':                                                              
            res = self.callmanager(sid, 'list_code_versions', False, {})                           
                                                                                           
            def add_cur(row):                                                                      
                if 'current' in row:                                                               
            	    row['current'] = '      *'                                                     
        	else:                                                                              
                    row['current'] = ''                                                            
                return row                                                                         
                                                                                           
            data = [ add_cur(el) for el in res['codeVersions'] ]                                   
            print self.prettytable(( 'current', 'codeVersionId', 'filename', 'description' ), data)
        
        if command == 'enable_code':
            try:                                         
                code_version = argv[3]                   
            except IndexError:                           
                self.usage(argv[0])                      
                sys.exit(0)                              
                                                 
            getattr(self, command)(sid, code_version)    


    def upload_code(self, service_id, filename):
        contents = open(filename).read()

        files = [ ( 'code', filename, contents ) ]

        res = self.callmanager(service_id, "/", True, { 'method': "upload_code_version",  }, files)
        if 'error' in res:
            print res['error']
        else:
            print "Code version %(codeVersionId)s uploaded" % res


    def enable_code(self, service_id, code_version):
        params = { 'codeVersionId': code_version }

        res = self.callmanager(service_id, "enable_code",
            True, params)

        if 'error' in res:
            print res['error']

        else:
            print code_version, 'enabled'
    
    def run(self, service_id):
        params = {}
        res = self.callmanager(service_id, "run", True, params)

        if 'error' in res:
            print res['error']
        else:
            print 'Service running'