#!/usr/bin/env python
# -*- coding: utf-8 -*-

#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
This script requires 4 environment variables to be declared:

    OS_USERNAME - Rackspace user for account that servers will be launched on
    OS_PASSWORD - API Key for the server launch user

    OS_DNS_USERNAME - Rackspace user with the tmpnb.org domain
    OS_DNS_PASSWORD - API key for the DNS user

Then to run, you specify which node number we're creating like demo-iad-001.tmpnb.org

python script/launch.py 10

The Ansible inventory file is spat out to stdout at the end.
'''

import binascii
import os

import pyrax

def name_new_nodes(prefix="demo", region="dfw", node_num=1, domain="tmpnb.org"):
    # The naming problem
    #node_naming_scheme = "{prefix}-{region}-{node_num:03}"
    node_naming_scheme = "{prefix}{node_num:02}"
    node_base_name = node_naming_scheme.format(**locals())

    user_server_name  = node_base_name + "-user" + "." + domain
    proxy_server_name = node_base_name + "." + domain

    return user_server_name, proxy_server_name

def launch_node(prefix="demo", region="iad", node_num=1, domain="tmpnb.org"):
    key_name = "main"

    pyrax.set_setting("identity_type", "rackspace")
    pyrax.set_credentials(os.environ["OS_USERNAME"], os.environ["OS_PASSWORD"])

    cs = pyrax.connect_to_cloudservers(region=region.upper())

    # My least favorite bug in pyrax - silent errors
    if(cs is None):
        raise Exception("Unable to connect to given region '{}'".format(region))

    # Get our base images
    images = cs.list_base_images()
    ubs = [image for image in images if "Ubuntu 14.04" in image.name]
    user_image = [image for image in ubs if "OnMetal" in image.name][0]
    proxy_image = [image for image in ubs if "PVHVM" in image.name][0]

    user_server_name, proxy_server_name = name_new_nodes(prefix=prefix,
                                                         region=region.lower(),
                                                         node_num=node_num,
                                                         domain=domain)

    # Launch the servers
    proxy_server = cs.servers.create(proxy_server_name, image=proxy_image.id, flavor='performance2-15', key_name=key_name)
    user_server = cs.servers.create(user_server_name, image=user_image.id, flavor='onmetal-memory1', key_name=key_name)

    # Wait on them
    print("Waiting on Proxy server")
    proxy_server = pyrax.utils.wait_for_build(proxy_server, verbose=True)
    print("Waiting on Notebook User server")
    user_server = pyrax.utils.wait_for_build(user_server, verbose=True)

    # Making this in case we want some JSON
    node_layout = {
        'notebook_server': {
            'private': user_server.networks['private'][0],
            'public': user_server.networks['public'][0]
        },
        'proxy_server': {
            'public': proxy_server.networks['public'][0]
        }
    }

    inventory = '''[notebook]
{user_server_name} ansible_ssh_user=root ansible_ssh_host={notebook_server_public} configproxy_auth_token={token} notebook_host={notebook_server_private}

[proxy]
{proxy_server_name} ansible_ssh_user=root ansible_ssh_host={proxy_server_public} notebook_host={notebook_server_private}
'''.format(notebook_server_public=user_server.accessIPv4,
           notebook_server_private=user_server.networks['private'][0],
           proxy_server_public=proxy_server.accessIPv4,
           token=binascii.hexlify(os.urandom(24)),
           user_server_name=user_server_name,
           proxy_server_name=proxy_server_name,
    )
    
    inventory_name = 'inventory-%s' % proxy_server_name
    with open(inventory_name, 'w') as f:
        f.write(inventory)
    
    print("Deploy tmpnb on this node with with:")
    print("  INVENTORY=%s ./script/deploy" % inventory_name)

    # If a separate account is used for DNS, use that instead
    if("OS_DNS_USERNAME" in os.environ and "OS_DNS_PASSWORD" in os.environ):
        pyrax.set_credentials(os.environ["OS_DNS_USERNAME"], os.environ["OS_DNS_PASSWORD"])

    dns = pyrax.cloud_dns.find(name=domain)
    dns.add_record({'type': 'A',
                    'name': proxy_server_name,
                    'ttl': 60*5,
                    'data': proxy_server.accessIPv4})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Launch nodes for tmpnb')

    parser.add_argument('--prefix', type=str, default='tmp',
                        help='prefix in the URL base')
    parser.add_argument('--region', type=str, default='dfw',
                        help='region to deploy to, also part of the domain name')
    parser.add_argument('node_num', type=int,
                        help='what this set of servers will be identified as numerically')
    parser.add_argument('--domain', type=str, default="tmpnb.org",
                        help='domain to host the servers on')

    args = parser.parse_args()
    launch_node(prefix=args.prefix, 
                region=args.region,
                node_num=args.node_num,
                domain=args.domain
    )

