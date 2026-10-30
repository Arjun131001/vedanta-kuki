# Create EC2 and deploy Vedanta

Prepared for Sydney (`ap-southeast-2`) and registered hostname `vedant-a.duckdns.org`. These files do not by themselves launch AWS resources.

## 1. Launch the infrastructure

Sign in to AWS and confirm remaining credits/expiry in Billing. In Sydney, open EC2 → Key pairs and create an ED25519 key pair in PEM format if you do not already have one. Keep the downloaded private key locally; do not send it in chat.

Open CloudFormation → Create stack → With new resources → Upload a template file. Upload `deploy/ec2-cloudformation.json`. Set:

| Field | Value |
| --- | --- |
| Stack name | `vedanta-demo` |
| VpcId | Your default VPC, or an existing VPC |
| SubnetId | Public subnet in that same VPC with an Internet Gateway route |
| KeyName | The key pair you just created or already own |
| AdminCidr | Your current public IPv4 plus `/32` |
| InstanceType | `t3.micro` only after confirming eligibility/price; `t3.small` has more memory and costs more |
| UbuntuAmi | Leave the Canonical Ubuntu 24.04 public parameter default |

If there is no existing VPC/public subnet, stop here and configure a VPC with an Internet Gateway first. The template does not create a paid NAT gateway or load balancer. Review EC2, 15 GiB gp3 storage and public IPv4 costs before submitting. Free account eligibility is not guaranteed by this template.

The stack creates one EC2 instance and a security group. SSH is limited to AdminCidr; only 80/443 are public. IMDSv2 is required, EBS is encrypted, and burst credits use standard mode. Docker installation runs through cloud-init. CREATE_COMPLETE does not mean cloud-init or application startup has finished. The script checks `/opt/vedanta/bootstrap-complete` before upload; installation logs are `/var/log/cloud-init-output.log`.

The instance and root volume are deliberately retained on stack deletion to protect data. This means deleting the stack is **not** a cost shutdown: explicitly terminate the retained instance and remove unneeded EBS volumes after backup. A stack deletion may also leave its referenced security group behind. Do not repeatedly create stacks to retry application setup; reuse the instance.

## 2. Upload application source

From the project folder in PowerShell, substitute the stack Outputs → PublicIp and local private-key path:

```powershell
.\deploy\publish.ps1 -PublicIp 'EC2_PUBLIC_IPV4' -PrivateKey 'C:\path\to\your-key.pem'
ssh -i 'C:\path\to\your-key.pem' ubuntu@EC2_PUBLIC_IPV4
```

Verify the SSH fingerprint against EC2 before accepting a new host. If SSH is blocked after your internet IP changes, update AdminCidr in the stack to your new `/32` address. The package uses an allowlist and excludes local data and credentials. No Git commit or repository publication is required.

## 3. Configure secrets on EC2

In the SSH session:

```bash
cd /opt/vedanta/deploy
cp -n .env.example .env
cp -n runtime.env.example runtime.env
chmod 600 .env runtime.env
sudo docker run --rm -it caddy:2.10-alpine caddy hash-password
nano .env
```

Paste the generated hash into DEMO_PASSWORD_HASH with single quotes around it. Set a unique RELEASE_TAG and keep DOMAIN=`vedant-a.duckdns.org`. The browser login username is `vedanta`. Optionally edit `runtime.env` with an OpenAI key for paid model features. Do not put any credentials in the CloudFormation template or user-data script.

```bash
sudoedit /etc/vedanta/duckdns.env
```

Enter:

```dotenv
DUCKDNS_SUBDOMAIN=vedant-a
DUCKDNS_TOKEN=YOUR_REAL_TOKEN
```

The token comes from your signed-in DuckDNS account. Configure it only on the server. Leave IPv6 empty in DuckDNS unless you deliberately configure IPv6 reachability.

## 4. Start and verify

```bash
sudo bash /opt/vedanta/deploy/start-server.sh
```

This updates DuckDNS to EC2, enables the updater timer, builds images, validates Caddy and starts the three containers. Allow time for DNS propagation and certificate issuance. A micro instance may run out of memory during building; in that case build/load images from a compatible Docker machine as described in `README.md`, or choose a larger instance after reviewing cost. Do not repeatedly retry a memory-exhausting build.

```bash
cd /opt/vedanta/deploy
sudo docker compose ps
curl --silent --output /dev/null --write-out '%{http_code}\n' https://vedant-a.duckdns.org/api/health
curl --fail --user vedanta https://vedant-a.duckdns.org/api/health
```

Expect 401 without credentials, then healthy JSON after entering the password. Open the website and test PDF/XLSX upload, worker extraction and evidence. Verify restart persistence. For logs use `sudo docker compose logs --tail 100`. For backups use `sudo bash backup.sh` and transfer the archive off EC2 securely. See `README.md` for restoration and rollback.

## References

- EC2 launch parameters: https://docs.aws.amazon.com/cli/latest/reference/ec2/run-instances.html
- Official Docker Ubuntu installation: https://docs.docker.com/engine/install/ubuntu/
