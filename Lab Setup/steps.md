> DISCLAIMER: All of this document is written after the fact so some information might not be in the right order as I'm relying on logs / search history / command history to create a timeline I can follow

# Everything Used

- Two Ubuntu Servers 24.04 VMs (one for server and one for agent)
- VirtulaBox (personal prefrence)
- Elasticsearch (9.3.3)
- Elastic-agent (8.17)
- Kibana (9.3.2)

# High Level Explanation
There are three main components for the elastic stack:

- **Elasticsearch**
The main database and search engine for the elastic stack, also has a component called fleet responsible for managing all connected agents

- **Kibana**
The web UI where you search, visualize, and manage all the collected logs, also let's you manage pretty much everything elasticsearch related.

- **Elasticagent**
It's one unified configurable agent that can collect everything replacing the need for multiple Beats in the past

# Base Installation
Download the Ubuntu Server image from the website and install it (don't overthink this part) and then install elastic by:
1. import the PGP key
```
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo gpg --dearmor -o /usr/share/keyrings/elasticsearch-keyring.gpg
```
2. Add the repo to the source list and install Elasticsearch
```bash
sudo apt install apt-transport-https
echo "deb [signed-by=/usr/share/keyrings/elasticsearch-keyring.gpg] https://artifacts.elastic.co/packages/9.x/apt stable main" | sudo tee /etc/apt/sources.list.d/elastic-9.x.list
sudo apt-get update && sudo apt-get install elasticsearch
```

Now it's worth mentioning that in my case the installation would always get stuck at 20% and after a healthy amount of mental gymnastics (this will be a recurring theme here) I found out that dpkg was stuck after running
siem@SIEM:~$ ps aux | grep -E "kibana|dpkg|apt"
root        1745  0.0  0.0  16736  7120 pts/2    S+   16:36   0:00 sudo apt install kibana
root        1746  0.0  0.0  16736  2520 pts/3    Ss   16:36   0:00 sudo apt install kibana
root        1747  0.1  1.1 105040 92844 pts/3    S+   16:36   0:00 apt install kibana
root        1794  2.4  0.7  66928 63124 pts/4    Ds+  16:36   0:15 /usr/bin/dpkg --status-fd 44 --no-triggers --unpack --auto-deconfigure /var/cache/apt/archives/kibana_9.3.2_amd64.deb
root        1795  0.0  0.0   2800  1848 pts/4    S+   16:36   0:00 sh -c -- (test -x /usr/lib/needrestart/dpkg-status && /usr/lib/needrestart/dpkg-status || cat > /dev/null)
root        1796  0.0  0.0   2800   912 pts/4    S+   16:36   0:00 sh -c -- (test -x /usr/lib/needrestart/dpkg-status && /usr/lib/needrestart/dpkg-status || cat > /dev/null)
root        1797  0.0  0.0   2800  1856 pts/4    S+   16:36   0:00 /bin/sh /usr/lib/needrestart/dpkg-status
siem        1832  0.0  0.0   6544  2332 pts/1    S+   16:46   0:00 grep --color=auto -E kibana|dpkg|apt

The D in the stat column according to the man pages:
"
PROCESS STATE CODES
       Here are the different values that the s, stat and state output specifiers (header "STAT" or "S") will display to describe the state of a process:

               **D uninterruptible sleep (usually IO)**
               I    Idle kernel thread
               R    running or runnable (on run queue)
               S    interruptible sleep (waiting for an event to complete)
               T    stopped by job control signal
               t    stopped by debugger during the tracing
               W    paging (not valid since the 2.6.xx kernel)
               X    dead (should never be seen)
               Z    defunct ("zombie") process, terminated but not reaped by its parent
"
So I needed to enable Host I/O caching which helped greatly, but other people reported various problems with slow install times such as this [github issue](https://github.com/elastic/kibana/issues/88138)

Now I'd recommend that from now on you run an admin shell because we'll do a lot of work inside */usr/share/bin/elasticsearch* specifically the bin directory which has a lot of binaries we'll use and also the main elasticsearch.yml is at */etc/elasticsearch* or keep using sudo

In this project I'm running a single node cluster meaning I have one instance of elasticsearch running for the current agent and any other agents that might join in the future.

We're almost done with elasticsearch but we need to enable it's service by running
```
sudo /bin/systemctl daemon-reload
sudo /bin/systemctl enable elasticsearch.service
```
and also reset the password used for the elastic user which we'll use in the future with kibana and also here

```
bin/elasticsearch-reset-password -u elastic 
```
store the output as an environment variable by editing your bash.rc in your home folder (this can change depending on what shell you're using)


To ensure that elasticsearch is set up well you can run this request from the terminal
```
sudo curl --cacert /etc/elasticsearch/certs/http_ca.crt -u elastic:$ELASTIC_PASSWORD https://localhost:9200
```
and you should see output like this
```
{
  "name" : "Cp8oag6",
  "cluster_name" : "elasticsearch",
  "cluster_uuid" : "AT69_T_DTp-1qgIJlatQqA",
  "version" : {
    "number" : "9.0.0-SNAPSHOT",
    "build_type" : "tar",
    "build_hash" : "f27399d",
    "build_flavor" : "default",
    "build_date" : "2016-03-30T09:51:41.449Z",
    "build_snapshot" : false,
    "lucene_version" : "10.0.0",
    "minimum_wire_compatibility_version" : "1.2.3",
    "minimum_index_compatibility_version" : "1.2.3"
  },
  "tagline" : "You Know, for Search"
}
```

# Installing Kibana
We already have the repository set up so just run ```sudo apt install kibana```
After it's installed just edit /etc/kibana/kibana.yml so that server.host has the machine's ip on a specific interface or just go with 0.0.0.0 to make it listen to everything and then run /usr/share/kibana/bin/kibana-setup and follow the instructions
The program will ask for an enrollment token which you can get by running ```/usr/share/elasticsearch/bin/elasticsearch-create-enrollment-token -s kibana```, An enrollment token is a temporary, one-time-use credential that Elasticsearch generates so that it can authenticate new nodes or in our case Kibana when it's being set up
Navigate to the kibana webpage and if it asks you for a verification code generate it with ```sudo /usr/share/kibana/bin/kibana-verification-code```
You're now supposed to be done according to the docs but in my case these were some of the logs

```
Mar 25 17:54:19 SIEM kibana[3278]: [2026-03-25T17:54:19.587+00:00][INFO ][plugins.fleet] Beginning fleet setup
Mar 25 17:54:19 SIEM kibana[3278]: [2026-03-25T17:54:19.587+00:00][INFO ][plugins.fleet] Cleaning old indices
Mar 25 17:54:19 SIEM kibana[3278]: [2026-03-25T17:54:19.618+00:00][WARN ][plugins.fleet] Fleet setup attempt 12 failed, will retry after backoff FleetEncryptedSavedObjectEncryptionKeyRequired: Agent binary source needs encrypted saved object api key to be set
```

Fleet was just complaining about encryption keys to store it's api keys safely which can be easily solved by running ```sudo /usr/share/kibana/bin/kibana-encryption-keys generate``` and using these values at then end of the kibana.yml file


# Installing Agents with TLS

1. Open Kibana at http://[VM1-IP]:5601 then go to **Fleet** from the sidebar -> **Agents** -> **Add agent** button


You'll be prompted to create or select an agent policy, feel free to do as you wish here and choose your system architecture, then you'll have a command as output which you'll need to paste into the machine you're trying to enroll but we'll add some stuff to make it work with SSL

The installation command would look something like this (I'm using 8.17.4 because 9.x would keep crashing on startup which I identified from the logs by running systemctl status elasticagent)
```bash
curl -L -O https://artifacts.elastic.co/downloads/beats/elastic-agent/elastic-agent-8.17.4-linux-x86_64.tar.gz
tar xzf elastic-agent-8.17.4-linux-x86_64.tar.gz
cd elastic-agent-8.17.4-linux-x86_64
sudo ./elastic-agent install --url=https://[VM1-IP]:8220 --enrollment-token=[TOKEN_FROM_KIBANA]
```
For now run everything but the last line and keep that page open as if we look at the docs for configuring secure connections we'll take a couple steps back to set it up and get back to this step

# Configuring TLS

First of all we need certificate authority that enables us to make different certificates for anything else which we can do by ```sudo /usr/share/elasticsearch/bin/elasticsearch-certutil ca --pem --out /home/siem/ca.zip``` and then we can generate a certificate for fleet server using the ca by ```sudo ./bin/elasticsearch-certutil cert   --name fleet-server   --ca-cert /home/siem/ca/ca.crt   --ca-key /home/siem/ca/ca.key   --dns siem   --ip 192.168.100.89   --pem --out /home/siem/fleet-server.zip``` and I'm using specific output locations because we'll need those in a second 

Now if you remember I mentioned that we'll need a different command to install elastic-agent than the one provided on kibana, this is what I was referring to. Checking the docs shows the command needs to look like this
```
sudo ./elastic-agent install \
   --url=https://192.168.100.x:8220 \
   --fleet-server-es=https://192.168.100.x:9200 \
   --fleet-server-service-token=ServiceTokenGoesHere \
   --fleet-server-policy=fleet-server-policy \
   --fleet-server-es-ca=/path/to/elasticsearch-ca.crt \
   --certificate-authorities=/path/to/ca.crt \
   --fleet-server-cert=/path/to/fleet-server.crt \
   --fleet-server-cert-key=/path/to/fleet-server.key \
   --fleet-server-port=8220 \
   --elastic-agent-cert=/tmp/fleet-server.crt \
   --elastic-agent-cert-key=/tmp/fleet-server.key \
   --elastic-agent-cert-key-passphrase=/tmp/fleet-server/passphrase-file \
   --fleet-server-es-cert=/tmp/fleet-server.crt \
   --fleet-server-es-cert-key=/tmp/fleet-server.key \
   --fleet-server-client-auth=required 
```


After you've done all the steps mentioned you should see the agent with status: **Healthy**, if you click the agent name you can see:
   - Last activity timestamp
   - Policy assigned
   - Agent version
   - Collected data status

To make sure data is being collected you can go to **Discover** in Kibana and select an index pattern like `metrics-elastic_agent*` or `logs-*` where you should find recent documents from your agent with:
   - `host.name`: Your agent machine name
   - `@timestamp`: Recent timestamps
   - System metrics or logs depending on your policy

# Refrences
[Installing Elasticsearch](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-with-debian-package)
[Installing Kibana](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-kibana-with-debian-package)
[Installing ElasticSearch & Kibana (medium)](https://medium.com/@enleak/configuring-elasticsearch-kibana-part-1-4d5d2e17ec7e)
[Installing Elastic Agent](https://www.elastic.co/docs/reference/fleet/install-fleet-managed-elastic-agent)
[SSL/TLS](https://www.elastic.co/docs/reference/fleet/secure-connections)
