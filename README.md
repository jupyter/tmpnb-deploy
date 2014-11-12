# tmpnb deployment

This repository contains an Ansible playbook for launching assets to *.tmpnb.org.

Single tmpnb setup is currently:

* nginx on one server for SSL termination, has a DNS record associated
* tmpnb on another server

Outside of those, we use the [tmpnb-redirector](https://github.com/jupyter/tmpnb-redirector) to redirect to these nodes. This Ansible playbook doesn't set that up (yet).

This is also set up for our own use, which means it may not work well for your own deployment (until we abstract it a bit further).

## Launching with Ansible

:warning: Note: you'll need to install Ansible from source (`devel` branch) to get the current versions of the Docker modules.

### Easy mode

```
script/deploy
```

### Directly, assuming you have secrets.yml available

```
ansible-playbook site.yml -i inventory
```


## Manual configuration

Launch an OnMetal Compute machine using Ubuntu 14.04 then roll through this:

```
apt-get update && apt-get install -y vim
apt-get upgrade -y #yolo
sed -i 's/GRUB_CMDLINE_LINUX=.*/GRUB_CMDLINE_LINUX="cgroup_enable=memory swapaccount=1"/' /etc/default/grub
update-grub
curl -sSL https://get.docker.com/ubuntu/ | sudo sh
docker pull jupyter/nature-demo # Change your image here
docker pull jupyter/configurable-http-proxy
docker pull jupyter/tmpnb
```

Edit `/etc/default/docker` to add `--icc=false --ip-forward=false` to `DOCKER_OPTS`.

```
reboot
```

### Launching

After everything above is done, launch the tmpnb setup, making sure to change `--image=jupyter/demo`

```
iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to 8000
docker run -d --name configproxy --net=host -e CONFIGPROXY_AUTH_TOKEN=LEGIT_KEY jupyter/configurable-http-proxy --default-target http://127.0.0.1:9999
docker run -d --name tmpnb --net=host -e CONFIGPROXY_AUTH_TOKEN=LEGIT_KEY -v /var/run/docker.sock:/docker.sock jupyter/tmpnb python orchestrate.py --cull-timeout=120 --docker-version=1.13 --pool-size=512 --image=jupyter/demo --static-files=/srv/ipython/IPython/html/static/ --redirect-uri=/tree --command='ipython3 notebook --NotebookApp.base_url={base_path}' --max-dock-workers=8
```


### tmpnb nginx setup

This host should have its own DNS record for the redirector to point to, e.g. yetanother.tmpnb.org

```
apt-get update && apt-get upgrade -y && apt-get install nginx
mkdir -p /var/www/tmpnb-static && cd /var/www/tmpnb-static
# Grab the static.tar *somehow*
tar -xvf static.tar

# Grab the nginx configuration *somehow*
cp nginx.conf /etc/nginx/sites-available/default
# Change the nginx configuration to point to the tmpnb node that this server goes with

# Put the certs in `/etc/ssl`

service nginx restart
```

