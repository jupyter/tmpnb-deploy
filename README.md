# tmpnb deployment

This repository contains an Ansible playbook for launching assets to *.tmpnb.org.

Single [tmpnb](https://github.com/jupyter/tmpnb) setup is currently:

* nginx on one server for SSL termination, has a DNS record associated
* tmpnb on another server

Outside of those, we use the [tmpnb-redirector](https://github.com/jupyter/tmpnb-redirector) to redirect to these nodes.

This is also set up for our own use, which means it may not work well for your own deployment (until we abstract it a bit further).

## Launching with Ansible

### "Easy" mode

```
source ./novarc
./script/new-instance <N>
```

This will:

- allocate new servers (./script/launch.py)
- add them to the redirector (./script/add-redirect)
- deploy tmpnb (./script/deploy)

### Updating images on a running instance

 ```bash
 ./script/image-update <N>
 ```
 

### Status page

The status page daemon for tmpnb availability is run on the tmpnb-status carina cluster.

You will need to get the API key from statuspage.io, and create `statuspage-env` with:

    STATUS_PAGE_API_KEY=<the-api-key>

Run:

    eval $(carina env tmpnb-status)
    ./script/launch-statuspage

To launch the statuspage daemons.
