#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
This script requires 4 environment variables to be declared:

    OS_USERNAME - Rackspace user for account that servers will be launched on
    OS_PASSWORD - API Key for the server launch user

    CF_API_KEY - CloudFlare API key
    CF_EMAIL - CloudFlare email address

    OS_DNS_USERNAME - Rackspace user with the tmpnb.org domain
    OS_DNS_PASSWORD - API key for the DNS user

Then to run, you specify which node number we're creating like demo-iad-001.tmpnb.org

python script/launch.py 10

The Ansible inventory file is spat out to stdout at the end.
'''

import binascii
import json
import os
import time

from rackspace.connection import Connection
import requests


CF_API_URL = 'https://api.cloudflare.com/client/v4/'


def cf_get_zone_id(s, domain):
    """Get cloudflare zone id"""
    r = s.get(CF_API_URL + 'zones?name=%s' % domain)
    r.raise_for_status()
    return r.json()['result'][0]['id']


def get_dns(s, zone_id):
    r = s.get(CF_API_URL + 'zones/%s/dns_records' % zone_id)
    r.raise_for_status()
    records = {}
    for res in r.json()['result']:
        records[res['name']] = res
    return records


def add_dns(name, ipv4):
    """Add DNS record with cloudflare"""
    s = requests.session()
    s.headers = {
        'X-Auth-Key': os.environ['CF_API_KEY'],
        'X-Auth-Email': os.environ['CF_EMAIL'],
    }
    domain = '.'.join(name.split('.')[-2:])
    print(domain)
    zone_id = cf_get_zone_id(s, domain)
    r = s.post(CF_API_URL + 'zones/%s/dns_records' % zone_id, data=json.dumps({
        'type': 'A',
        'name': name,
        'content': ipv4,
    }))
    r.raise_for_status()


def name_new_nodes(prefix="demo", region="dfw", node_num=1, domain="tmpnb.org"):
    # The naming problem
    #node_naming_scheme = "{prefix}-{region}-{node_num:03}"
    node_naming_scheme = "{prefix}{node_num:02}"
    node_base_name = node_naming_scheme.format(**locals())

    user_server_name  = node_base_name + "-user" + "." + domain
    proxy_server_name = node_base_name + "." + domain

    return user_server_name, proxy_server_name


def print_server_status(server):
    print("{name} {status} progress={progress}".format(
        name=server.name,
        status=server.status,
        progress=server.progress,
    ))


def wait_for_server(compute, server, timeout=600, interval=10):
    # rackspacesdk wait_for_server doesn't work!
    tic = time.monotonic()
    while time.monotonic() - tic < timeout and server.status != 'ACTIVE':
        print_server_status(server)
        time.sleep(interval)
        server = list(compute.servers(name=server.name))[0]

    if server.status != 'ACTIVE':
        raise TimeoutError("{name} is still {status}".format(
            name=server.name,
            status=server.status))
    print_server_status(server)
    return server


def launch_node(prefix="demo", region="dfw", node_num=1, domain="tmpnb.org"):
    key_name = "main"

    rs = Connection(
        username=os.environ['OS_USERNAME'],
        api_key=os.environ['OS_PASSWORD'],
        region=region.upper(),
    )


    compute = rs.compute


    # Get our base images
    images = compute.images()
    ubs = [image for image in images if "Ubuntu 14.04" in image.name]
    user_image = [image for image in ubs if "OnMetal" in image.name][0]
    proxy_image = [image for image in ubs if "PVHVM" in image.name][0]
    # Get our flavors
    flavors = list(compute.flavors())
    proxy_flavor = [flavor for flavor in flavors if flavor.ram == 8192 and "General Purpose" in flavor.name][0]
    user_flavor = [flavor for flavor in flavors if "OnMetal" in flavor.name and "Medium" in flavor.name][0]
    print("Proxy: %s" % proxy_flavor.name)
    print(" User: %s" % user_flavor.name)

    user_server_name, proxy_server_name = name_new_nodes(prefix=prefix,
                                                         region=region.lower(),
                                                         node_num=node_num,
                                                         domain=domain)

    # Launch the servers
    try:
        user_server = next(iter(compute.servers(name=user_server_name)))
    except StopIteration:
        user_server = compute.create_server(name=user_server_name, imageRef=user_image.id, flavorRef=user_flavor.id, key_name=key_name)
    else:
        print("User server %s already started" % user_server_name)

    try:
        proxy_server = next(iter(compute.servers(name=proxy_server_name)))
    except StopIteration:
        proxy_server = compute.create_server(name=proxy_server_name, imageRef=proxy_image.id, flavorRef=proxy_flavor.id, key_name=key_name)
    else:
        print("Proxy server %s already started" % proxy_server_name)

    # Wait on them
    print("Waiting on Proxy server")
    proxy_server = wait_for_server(compute, proxy_server)
    print("Waiting on Notebook User server")
    user_server = wait_for_server(compute, user_server)

    # create ping alarms
    ping_alarm(proxy_server)
    ping_alarm(user_server)

    inventory = '''[notebook]
{user_server_name} ansible_ssh_user=root ansible_ssh_host={notebook_server_public} configproxy_auth_token={token} notebook_host={notebook_server_private}

[proxy]
{proxy_server_name} ansible_ssh_user=root ansible_ssh_host={proxy_server_public} notebook_host={notebook_server_private}
'''.format(notebook_server_public=user_server.access_ipv4,
           notebook_server_private=user_server.addresses['private'][0]['addr'],
           proxy_server_public=proxy_server.access_ipv4,
           token=binascii.hexlify(os.urandom(24)).decode('ascii'),
           user_server_name=user_server_name,
           proxy_server_name=proxy_server_name,
    )

    inventory_name = 'inventory.%i' % node_num
    with open(inventory_name, 'w') as f:
        f.write(inventory)

    print("Deploy tmpnb on this node with with:")
    print("  INVENTORY=%s ./script/deploy" % inventory_name)

    add_dns(proxy_server_name, proxy_server.access_ipv4)


PING_ALARM_CRITERIA = """
if (metric['available'] < 20) {
  return new AlarmStatus(CRITICAL, 'Host appears to be unreachable');
}

return new AlarmStatus(OK, 'Packet loss is normal');
"""

def ping_alarm(server):
    """Add a ping alarm, so we get emails whenever a node appears to go down."""
    from rackspace_monitoring.providers import get_driver
    from rackspace_monitoring.types import Provider
    RaxMon = get_driver(Provider.RACKSPACE)
    cm = RaxMon(os.environ['OS_USERNAME'], os.environ['OS_PASSWORD'])
    notification_plan = cm.list_notification_plans()[0]
    # get monitoring entities

    # get ping check
    pings = []
    while not pings:
        entities = [ e for e in cm.list_entities() if e.label == server.name ]
        pings = [ e for e in entities if cm.list_checks(e) and 'ping' in cm.list_checks(e)[0].label.lower() ]
        if not pings:
            print('waiting for ping check to be registered')
            print([cm.list_checks(e)[0].label.lower() for e in entities])
            time.sleep(1)
    ping = pings[0]
    ping_check = cm.list_checks(ping)[0]

    cm.create_alarm(ping,
        check_id=ping_check.id,
        notification_plan_id=notification_plan.id,
        criteria=PING_ALARM_CRITERIA,
        label='ping')


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

