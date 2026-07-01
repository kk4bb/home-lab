# Elastic Stack Deployment with Fleet and TLS

> **Disclaimer:** This document was written after the deployment was completed. Some events may not appear in their exact chronological order because the timeline was reconstructed from command history, logs, and browser history.

# Environment

## Infrastructure

* 2 Ubuntu Server 24.04 virtual machines
  * VM1: Elasticsearch, Kibana, Fleet Server
  * VM2: Elastic Agent
* VirtualBox (personal preference)

## Software Versions
* Elasticsearch 9.3.3
* Kibana 9.3.2
* Elastic Agent 8.17.x

> **Note:** During testing, Elastic Agent 9.x repeatedly crashed during startup. Fleet Server and agents were therefore deployed using version 8.17.x.

# High-Level Overview

The Elastic Stack consists of three primary components:

## Elasticsearch

Elasticsearch is the database and search engine that stores and indexes collected data.

## Kibana

Kibana provides the web interface used to:

* Search collected data
* Create visualizations and dashboards
* Configure Fleet
* Manage integrations and policies
* Administer Elasticsearch

## Elastic Agent

Elastic Agent is a unified data collection agent that replaces multiple Beats and can collect:

* System metrics
* Logs
* Security telemetry
* Application data

Fleet management is performed through Kibana while Elasticsearch serves as the backend storage layer.

# Network Requirements

Ensure the following ports are reachable:

| Service       | Port     |
| ------------- | -------- |
| Elasticsearch | 9200/TCP |
| Kibana        | 5601/TCP |
| Fleet Server  | 8220/TCP |

To verify listening services:
```bash
ss -tulpn
```

# Installing Elasticsearch

## Add the Repository

Import the Elastic signing key:

```bash
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | \
sudo gpg --dearmor -o /usr/share/keyrings/elasticsearch-keyring.gpg
```

Install required packages and add the repository:

```bash
sudo apt install apt-transport-https

echo "deb [signed-by=/usr/share/keyrings/elasticsearch-keyring.gpg] \
https://artifacts.elastic.co/packages/9.x/apt stable main" | \
sudo tee /etc/apt/sources.list.d/elastic-9.x.list

sudo apt update
sudo apt install elasticsearch
```

## VirtualBox Installation Issue

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

Enabling **Host I/O Cache** in VirtualBox significantly improved installation performance.

Other users have reported similar behavior during Elastic package installation.

## Enable and Start Elasticsearch

```bash
sudo systemctl daemon-reload
sudo systemctl enable elasticsearch
sudo systemctl start elasticsearch
```

Verify service status:

```bash
sudo systemctl status elasticsearch
```

## Reset the Elastic Password

Generate a new password for the built-in `elastic` user:

```bash
sudo /usr/share/elasticsearch/bin/elasticsearch-reset-password -u elastic
```

Store the generated password as an environment variable, for example in `.bashrc`:

```bash
export ELASTIC_PASSWORD="<PASSWORD>"
```

Reload the shell:

```bash
source ~/.bashrc
```

## Verify Elasticsearch

```bash
sudo curl \
--cacert /etc/elasticsearch/certs/http_ca.crt \
-u elastic:$ELASTIC_PASSWORD \
https://localhost:9200
```

A successful response should return cluster information in JSON format.

# Installing Kibana

Because the repository has already been configured:

```bash
sudo apt install kibana
```

## Configure Network Access

Edit ```/etc/kibana/kibana.yml```

Set Kibana to listen on the server IP or all interfaces:

```yaml
server.host: "0.0.0.0"
```

## Enroll Kibana

Generate an enrollment token:

```bash
sudo /usr/share/elasticsearch/bin/elasticsearch-create-enrollment-token -s kibana
```

Run Kibana setup:

```bash
sudo /usr/share/kibana/bin/kibana-setup
```

Enter the enrollment token when prompted.

If Kibana requests a verification code:

```bash
sudo /usr/share/kibana/bin/kibana-verification-code
```

Then start Kibana:

```bash
sudo systemctl enable kibana
sudo systemctl start kibana
```

# Generating TLS Certificates

A dedicated certificate authority (CA) will be used to sign certificates for:

* Elasticsearch
* Kibana
* Fleet Server

## Generate the Certificate Authority

```bash
sudo /usr/share/elasticsearch/bin/elasticsearch-certutil ca \
--pem \
--out /home/siem/ca.zip
```

Extract the archive.

## Generate Service Certificates

### Elasticsearch

```bash
sudo /usr/share/elasticsearch/bin/elasticsearch-certutil cert \
--name elasticsearch \
--ca-cert /home/siem/ca/ca.crt \
--ca-key /home/siem/ca/ca.key \
--dns ELASTICSEARCH_DNS \
--ip ELASTICSEARCH_IP \
--pem \
--out /home/siem/elasticsearch.zip
```

### Kibana

```bash
sudo /usr/share/elasticsearch/bin/elasticsearch-certutil cert \
--name kibana \
--ca-cert /home/siem/ca/ca.crt \
--ca-key /home/siem/ca/ca.key \
--dns KIBANA_DNS \
--ip KIBANA_IP \
--pem \
--out /home/siem/kibana.zip
```

### Fleet Server

```bash
sudo /usr/share/elasticsearch/bin/elasticsearch-certutil cert \
--name fleet-server \
--ca-cert /home/siem/ca/ca.crt \
--ca-key /home/siem/ca/ca.key \
--dns FLEET_SERVER_DNS \
--ip FLEET_SERVER_IP \
--pem \
--out /home/siem/fleet-server.zip
```

## Install Certificates

Copy certificates to their respective locations.

Example for Elasticsearch:

```bash
sudo cp ~/ca/ca.crt /etc/elasticsearch/certs/
sudo cp ~/elasticsearch/elasticsearch.crt /etc/elasticsearch/certs/
sudo cp ~/elasticsearch/elasticsearch.key /etc/elasticsearch/certs/

sudo chown -R elasticsearch:elasticsearch /etc/elasticsearch/certs/
```

Example for Kibana:

```bash
sudo cp ~/kibana/kibana.crt /etc/kibana/
sudo cp ~/kibana/kibana.key /etc/kibana/

sudo chown kibana:kibana /etc/kibana/kibana.*
sudo chmod 600 /etc/kibana/kibana.key
```

## Generate Certificate Fingerprints

```bash
openssl x509 \
-in ./ca.crt \
-noout \
-fingerprint \
-sha256 \
| sed 's/://g' \
| sed 's/SHA256 Fingerprint=//' \
| tr '[:upper:]' '[:lower:]'
```

# Configuring TLS

## Elasticsearch

Edit ```/etc/elasticsearch/elasticsearch.yml```

Configure HTTPS:

```yaml
xpack.security.http.ssl:
  enabled: true
  certificate: /etc/elasticsearch/certs/elasticsearch.crt
  key: /etc/elasticsearch/certs/elasticsearch.key
  certificate_authorities:
    - /etc/elasticsearch/certs/ca.crt
```

> This deployment uses a single-node cluster. Therefore transport-layer TLS configuration is not required.

Restart Elasticsearch:

```bash
sudo systemctl restart elasticsearch
```

## Kibana

Edit ```/etc/kibana/kibana.yml```

Configure TLS:

```yaml
server.ssl.enabled: true
server.ssl.certificate: /etc/kibana/kibana.crt
server.ssl.key: /etc/kibana/kibana.key
```

To be able to edit the agent outputs through the UI, comment out the ouputs section ```xpack.fleet.outputs``` at the end of the file

Restart Kibana:

```bash
sudo systemctl restart kibana
```

You should now access Kibana using ```https://<KIBANA_IP>:5601```

# Configuring Fleet

Open Kibana and navigate to ```Fleet → Settings```

Configure:

* Fleet Server Hosts
* Outputs
* SSL CA Trusted Fingerprint

These settings will be used by future agents.

# Installing Fleet Server

Navigate to ```Fleet → Agents → Add Fleet Server```

Choose: ```Advanced → Production```

This allows custom TLS certificates.

Select or create a Fleet Server policy.

Kibana will generate an installation command.

Modify the command to include TLS parameters:

```bash
sudo ./elastic-agent install \
--url=https://<FLEET_SERVER_IP>:8220 \
--fleet-server-es=https://<ELASTICSEARCH_IP>:9200 \
--fleet-server-service-token=<TOKEN> \
--fleet-server-policy=fleet-server-policy \
--fleet-server-es-ca-trusted-fingerprint=<FINGERPRINT> \
--certificate-authorities=<PATH_TO_CA> \
--fleet-server-cert=<FLEET_SERVER_CERT> \
--fleet-server-cert-key=<FLEET_SERVER_KEY> \
--fleet-server-port=8220
```

# Installing Additional Agents

From ```Fleet → Agents → Add Agent```

Copy the enrollment command and modify it:

```bash
sudo elastic-agent install \
--url=https://<FLEET_SERVER_IP>:8220 \
--enrollment-token=<TOKEN> \
--certificate-authorities=<PATH_TO_CA>
```

# Verification

A healthy agent should appear under ```Fleet → Agents``` with status: Healthy

Agent details include:

* Last activity
* Assigned policy
* Agent version
* Data collection status

## Verify Data Collection

Navigate to ```Discover```

Common index patterns:

- logs-*
- metrics-*
- metrics-elastic_agent*

You should see documents containing fields such as:

- host.name
- @timestamp
- event.dataset

with recent timestamps and active telemetry.

# Useful Paths

## Elasticsearch

```text
/usr/share/elasticsearch/
/usr/share/elasticsearch/bin/
/etc/elasticsearch/
```

## Kibana

```text
/usr/share/kibana/
/usr/share/kibana/bin/
/etc/kibana/
```

# Refrences
[Installing Elasticsearch](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-with-debian-package)
[Installing Kibana](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-kibana-with-debian-package)
[Installing ElasticSearch & Kibana (medium)](https://medium.com/@enleak/configuring-elasticsearch-kibana-part-1-4d5d2e17ec7e)
[Installing Elastic Agent](https://www.elastic.co/docs/reference/fleet/install-fleet-managed-elastic-agent)
[SSL/TLS](https://www.elastic.co/docs/reference/fleet/secure-connections)
