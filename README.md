
If using Ubuntu (as in production right now), launch an OnMetal Memory machine using Ubuntu 14.04 then roll through this:

## Ubuntu configuration

Apply updates and #1 best admin tool

```
apt-get update && apt-get install -y vim
apt-get upgrade -y
sed -i 's/GRUB_CMDLINE_LINUX=.*/GRUB_CMDLINE_LINUX="cgroup_enable=memory swapaccount=1"/' /etc/default/grub
update-grub
curl -sSL https://get.docker.com/ubuntu/ | sudo sh
docker pull jupyter/nature-demo
docker pull jupyter/configurable-http-proxy
docker pull jupyter/tmpnb
reboot
```

### Launching

After everything above is done, launch the tmpnb setup:

```
iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to 8000
docker run -d --name configproxy --net=host -e CONFIGPROXY_AUTH_TOKEN=LEGIT_KEY jupyter/configurable-http-proxy --default-target http://127.0.0.1:9999
docker run -d --name tmpnb --net=host -e CONFIGPROXY_AUTH_TOKEN=LEGIT_KEY -v /var/run/docker.sock:/docker.sock jupyter/tmpnb python orchestrate.py --cull-timeout=120 --cull-period=240 --docker-version=1.13 --pool-size=512 --image=jupyter/nature-demo --static-files=/srv/ipython/IPython/html/static/ --redirect-uri=/notebooks/Nature.ipynb --command='ipython3 notebook --NotebookApp.base_url={base_path}' --max-dock-workers=8
```
