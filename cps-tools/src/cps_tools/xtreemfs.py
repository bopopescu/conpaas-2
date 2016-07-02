
import argcomplete
import logging
import sys

from .base import BaseClient
from .config import config
from .service import ServiceCmd

import base64

POLICIES = {'osd_sel': {'list': 'list_osd_sel_policies',
                        'set': 'set_osd_sel_policy',
                        },
            'replica_sel': {'list': 'list_replica_sel_policies',
                            'set': 'set_replica_sel_policy',
                            },
            'replication': {'list': 'list_replication_policies',
                            'set': 'set_replication_policy',
                            },
            }


class XtreemFSCmd(ServiceCmd):

    def __init__(self, xtreemfs_parser, client):
        ServiceCmd.__init__(self, xtreemfs_parser, client, "xtreemfs",
                            ['osd', 'mrc', 'dir'],
                            "XtreemFS service sub-commands help")
        self._add_add_xfs_volume()
        self._add_list_xfs_volumes()
        self._add_remove_xfs_volume()
        self._add_get_client_cert()
        self._add_get_user_cert()
        self._add_list_policies()
        self._add_set_policy()
        self._add_toggle_persistent()
        self._add_set_osd_size()

    # ========== list_xfs_volumes
    def _add_list_xfs_volumes(self):
        subparser = self.add_parser('list_xfs_volumes',
                                    help="list volumes of an XtreemFS service")
        subparser.set_defaults(run_cmd=self.list_xfs_volumes, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def list_xfs_volumes(self, args):
        app_id, service_id = self.check_service(args.app_name_or_id, args.serv_name_or_id)

        res = self.client.call_manager_get(app_id, service_id, "listVolumes")

        print "%s" % res['volumes']

    # ========== add_xfs_volume
    def _add_add_xfs_volume(self):
        subparser = self.add_parser('add_xfs_volume',
                                    help="add a volume to XtreemFS service")
        subparser.set_defaults(run_cmd=self.add_xfs_volume, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('volume_name', help="Name of volume")

    def add_xfs_volume(self, args):
        app_id, service_id = self.check_service(args.app_name_or_id, args.serv_name_or_id)

        data = {'volumeName': args.volume_name}
        self.client.call_manager_post(app_id, service_id, "createVolume", data)

        print("Volume %s has been added." % args.volume_name)

    # ========== remove_xfs_volume
    def _add_remove_xfs_volume(self):
        subparser = self.add_parser('remove_xfs_volume',
                                    help="remove volume from XtreemFS service")
        subparser.set_defaults(run_cmd=self.remove_xfs_volume, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('volume_name', help="Name of volume")

    def remove_xfs_volume(self, args):
        app_id, service_id = self.check_service(args.app_name_or_id, args.serv_name_or_id)

        data = {'volumeName': args.volume_name}
        self.client.call_manager_post(app_id, service_id, "deleteVolume", data)

        print("Volume %s has been successfully removed from XtreemFS service %d."
              % (args.volume_name, service_id))

    # ========== get_client_cert
    def _add_get_client_cert(self):
        subparser = self.add_parser('get_client_cert',
                                    help="create a PKCS#12 client certificate")
        subparser.set_defaults(run_cmd=self.get_client_cert, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('passphrase',
                               help="PKCS#12 passphrase")
        subparser.add_argument('adminflag',
                               help="Flag which grants administrator rights [ yes | no ]")
        subparser.add_argument('filename',
                               help="Name of the PKCS#12 certificate file to be generated")

    def get_client_cert(self, args):
        app_id, service_id = self.check_service(args.app_name_or_id, args.serv_name_or_id)

        data = { 'passphrase': args.passphrase,
                 'adminflag': str(args.adminflag).lower() in ("yes", "y", "true", "t", "1") }
        filename = args.filename
        res = self.client.call_manager_post(app_id, service_id, "get_client_cert", data)

        open(filename, 'wb').write(base64.b64decode(res['cert']))
        print("Client certificate '%s' has been successfully created from XtreemFS service %d."
              % (args.filename, service_id))

    # ========== get_user_cert
    def _add_get_user_cert(self):
        subparser = self.add_parser('get_user_cert',
                                    help="create a PKCS#12 user certificate")
        subparser.set_defaults(run_cmd=self.get_user_cert, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('user',
                               help="User name")
        subparser.add_argument('group',
                               help="Group name")
        subparser.add_argument('passphrase',
                               help="PKCS#12 passphrase")
        subparser.add_argument('adminflag',
                               help="Flag which grants administrator rights [ yes | no ]")
        subparser.add_argument('filename',
                               help="Name of the PKCS#12 certificate file to be generated")

    def get_user_cert(self, args):
        app_id, service_id = self.check_service(args.app_name_or_id, args.serv_name_or_id)

        data = {  'user': args.user,
                  'group': args.group,
                  'passphrase': args.passphrase,
                  'adminflag': str(args.adminflag).lower() in ("yes", "y", "true", "t", "1") }
        filename = args.filename
        res = self.client.call_manager_post(app_id, service_id, "get_user_cert", data)

        open(filename, 'wb').write(base64.b64decode(res['cert']))
        print("User certificate '%s' has been successfully created from XtreemFS service %d."
              % (args.filename, service_id))

    # ========== list_policies
    def _add_list_policies(self):
        subparser = self.add_parser('list_policies',
                                    help="List XtreemFS policies")
        subparser.set_defaults(run_cmd=self.list_policies, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('policy_type', choices=POLICIES.keys(),
                               help="Type of XtreemFS policy.")

    def list_policies(self, args):
        app_id, service_id = self.check_service(args.app_name_or_id, args.serv_name_or_id)

        res = self.client.call_manager_get(app_id, service_id, POLICIES[args.policy_type]['list'])

        print '%s' % res['policies']

    # ========== set_policy
    def _add_set_policy(self):
        subparser = self.add_parser('set_policy',
                                    help="Set an XtreemFS policy")
        subparser.set_defaults(run_cmd=self.set_policy, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('policy_type', choices=POLICIES.keys(),
                               help="Type of XtreemFS policy.")

    def set_policy(self, args):
        app_id, service_id = self.check_service(args.app_name_or_id, args.serv_name_or_id)

        res = self.client.call_manager_post(app_id, service_id, POLICIES[args.policy_type]['set'])

        print '%s' % res['stdout']

    # ========== toggle_persistent
    def _add_toggle_persistent(self):
        subparser = self.add_parser('toggle_persistent',
                                    help="Toggle persistency of an XtreemFS service")
        subparser.set_defaults(run_cmd=self.toggle_persistent, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def toggle_persistent(self, args):
        app_id, service_id = self.check_service(args.app_name_or_id, args.serv_name_or_id)

        res = self.client.call_manager_post(app_id, service_id, 'toggle_persistent')

        print '%s' % res['stdout']

    # ========== set_osd_size
    def _add_set_osd_size(self):
        subparser = self.add_parser('set_osd_size',
                                    help="Set a new size for an XtreemFS volume")
        subparser.set_defaults(run_cmd=self.set_osd_size, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('volume_size', type=int,
                               help="Size of volume in MB.")

    def set_osd_size(self, args):
        app_id, service_id = self.check_service(args.app_name_or_id, args.serv_name_or_id)

        if args.volume_size <= 0:
            raise Exception('Cannot resize a volume to %s MB.' % args.volume_size)

        data = {'size': args.volume_size}
        res = self.client.call_manager_post(app_id, service_id, 'set_osd_size', data)

        print "OSD volume size is now %s MBs" % res['osd_volume_size']


def main():
    logger = logging.getLogger(__name__)
    console = logging.StreamHandler()
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logger.addHandler(console)

    cmd_client = BaseClient(logger)

    parser, argv = config('Manage ConPaaS XtreemFS services.', logger)

    _serv_cmd = XtreemFSCmd(parser, cmd_client)

    argcomplete.autocomplete(parser)
    args = parser.parse_args(argv)
    cmd_client.set_config(args.director_url, args.username, args.password,
                          args.debug)
    try:
        args.run_cmd(args)
    except Exception:
        if args.debug:
            traceback.print_exc()
        else:
            ex = sys.exc_info()[1]
            if str(ex).startswith("ERROR"):
                sys.stderr.write("%s\n" % ex)
            else:
                sys.stderr.write("ERROR: %s\n" % ex)
        sys.exit(1)


if __name__ == '__main__':
    main()
