# Installation

## Requirements

* Nginx (Other possible when modifying the sample download section)
* Python 3 (Flask and other dependencies)
* MySQL
* Pure-FTPD with mysql

## Configuring Google Cloud Platform

To configure the GCP for the platform, see [the installation guide](ci-vm/installation.md).

## Automated install

Automated install only works for the platform section; make sure to have configured the GCP before continuing the platform installation.

## Creation of sample platform server instance

For deployment of the platform on a Google Cloud VM instance, one would require to create an instance and configure some network firewall settings. If you are deploying the platform on a local instance, you can skip these two steps.

1. Creating a VM instance

   - Open the Google Cloud console, navigate to Compute Engine -> VM instances section, and click on "Create Instance".
   - The following are the details of the VM instance to be entered (most of the default configuration below can be changed as per the requirements):
        - Region: us-central1 (Iowa)
        - Zone: us-central1-a
        - Machine Family: General Purpose
        - Series: E2
        - Machine Type: e2-small
        - Boot Disk
            - For Linux:
                - OS: Ubuntu
                - Version: Ubuntu 22.04 LTS (x86)
                - Boot type disk: Balanced persistent disk
                - Size: 10GB
            - For Windows:
                - OS: Windows Server
                - Version: 
Windows Server 2019 Datacenter
                - Boot type disk: Balanced persistent disk
                - Size: 50GB
        - Choose the service account as the service account you just created for the platform.
        - Select the "Allow HTTP traffic" and "Allow HTTPS traffic" checkboxes.
        - Navigate to Advanced options -> Networking -> Network Interfaces -> External IPv4 address, and click on Create IP Address and reserve a new static external IP address for the platform.

2. Setting up firewall settings
    
    To allow access to the platform through an external IPv4 address just created, there are some firewall configurations to be made:
    - Navigate to VPC network -> Firewall and click on "Create Firewall Rule".
    - Set the rule name as "default-allow-https" and enter the following details for this rule:
        - Priority: 1000
        - Direction of Traffic: Ingress
        - Action on the match: Allow
        - Target type: Specified target tags -> Target Tags: "https-server"
        - Source Filter: IPv4 ranges
        - Source IPv4 ranges: 0.0.0.0/0
        - Protocols and ports -> Specified protocols and ports -> TCP -> Port: 443  (Nginx server is configured on this port)
    - Now click on "Save"
    - Now create another firewall rule for HTTP as "default-allow-http" with the following changes in the above configuration:
        - Target type: Specified target tags -> Target Tags: "http-server"
        - Protocols and ports -> Specified protocols and ports -> TCP -> Port: 80


### Linux

Clone the latest sample-platform repository from 
https://github.com/CCExtractor/sample-platform.
Note that root (or sudo) is required for both installation and running the program.
The `sample-repository` directory needs to be accessible by `www-data`. The
recommended directory is thus `/var/www/`.

```
cd /var/www/
sudo git clone https://github.com/CCExtractor/sample-platform.git
```

### Mounting the bucket

Mounting on Linux OS can be done using [Google Cloud Storage FUSE](https://cloud.google.com/storage/docs/gcs-fuse).

Steps:
- Install gcsfuse using [official documentation](https://github.com/GoogleCloudPlatform/gcsfuse/blob/master/docs/installing.md) or using the following script 
    ```
    curl -L -O https://github.com/GoogleCloudPlatform/gcsfuse/releases/download/v0.39.2/gcsfuse_0.39.2_amd64.deb
    sudo dpkg --install gcsfuse_0.39.2_amd64.deb
    rm gcsfuse_0.39.2_amd64.deb
    ```
- Now, there are multiple ways to mount the bucket, official documentation [here](https://github.com/GoogleCloudPlatform/gcsfuse/blob/master/docs/mounting.md). 

    For Ubuntu and derivatives, assuming `/repository` to be the location of samples to be configured, an entry can be added to `/etc/fstab` file, replace _GCS_BUCKET_NAME_ with the name of the bucket created for the platform:
    ```
    echo "GCS_BUCKET_NAME   /repository 	gcsfuse rw,gid=33,noatime,async,_netdev,noexec,user,implicit_dirs,allow_other,file_mode=774,dir_mode=775	0 0" | sudo tee -a /etc/fstab
    ```

- Now run the following command as root to mount the bucket:
    ```
    sudo mkdir /repository
    sudo mount /repository
    ```

You may check if the mount was successful and if the bucket is accessible by running `ls /repository` command.

#### Troubleshooting: Mounting of Bucket

In case you get "permission denied" for `/repository`, you can check for the following reasons:
1. Check if the service account created has access to the GCS bucket.
2. Check the output of `sudo mount /repository` command.

Place the service account key file at the root of the sample-platform folder. 

#### MySQL installation
The platform has been tested for MySQL v8.0 and Python 3.7 to 3.9. 

It is recommended to install python and MySQL beforehand to avoid any inconvenience. Here is the [installation link](https://www.digitalocean.com/community/tutorials/how-to-install-mysql-on-ubuntu-22-04) of MySQL on Ubuntu 22.04.

Next, navigate to the `install` folder and run `install.sh` with root 
permissions.

```
cd sample-platform/install/
sudo ./install.sh
```    

The `install.sh` will begin downloading and updating all the necessary dependencies. Once done, it'll ask to enter some details in order to set up the sample-platform. After filling in these details, the platform should be ready for use.

Please read the below troubleshooting notes in case of any error or doubt.

### Windows

* Install cygwin (http://cygwin.com/install.html). When cygwin asks which
 packages to install, select Python, MySql, and google-api-client. If you 
 already have cygwin installed, you must run its setup file to install the new packages. Make sure the dropdown menu is set to Full, so you can all packages. To select one, click skip and it will change to the version number of the package. Use the end of [this](https://www.davidbaumgold.com/tutorials/set-up-python-windows/) tutorial for help on getting cygwin to recognize python.
* Install [WinFsp](https://winfsp.dev/) and [Rclone](https://rclone.org/) from their official websites.
* Now rclone is a command line program, follow the [official documentation](https://rclone.org/googlecloudstorage/) to mount the google cloud storage bucket, using the service account key file.
* By default home directory of Cygwin is `C:\cygwin\home\<USERNAME>\` (this can be obtained by running `cygpath -w ~` from cygwin terminal), and assuming `\repository` to be the location of samples to be configured, mount the bucket using rclone at `C:\cygwin\home\<USERNAME>\repository` through the following command using command prompt:
    ```
    rclone mount GCS_BUCKET_NAME MOUNT_LOCATION --no-console
    ```
* Start a terminal session once installation is complete.
* Install Nginx (see http://nginx.org/en/docs/windows.html) 
* Follow the steps from the Linux installation from within the Cygwin terminal
to complete the platform's installation.

### Troubleshooting

* The configuration of the sample platform assumes that no other application
already runs on port 80. A default installation of nginx leaves a `default` 
config file behind, so it's advised to delete that and stop other 
applications that use the port.

**Note : Do not forget to do `service nginx reload` and 
`service platform start` after making any changes to the nginx configuration
or platform configuration.**
* SSL is required. If the platform runs on a publicly accessible server, 
it's **recommended** to use a valid certificate. 
[Let's Encrypt](https://letsencrypt.org/) offers free certificates. For local
testing, a self-signed certificate can be enough.
* When the server name is asked during installation, enter the domain name 
that will run the platform. E.g., if the platform will run locally, enter 
`localhost` as the server name.
* In case of a `502 Bad Gateway` response, the platform didn't start 
correctly. Manually running `bootstrap_gunicorn.py` (as root!) can help to 
determine what goes wrong. The snippet below shows how this can be done:

```
cd /var/www/sample-platform/
sudo python bootstrap_gunicorn.py
```

* If `gunicorn` boots up successfully, most relevant logs will be stored in
 the `logs` directory. Otherwise they'll likely be in `syslog`.

* If any issue still persists, follow the mentioned steps to debug and troubleshoot your issue:
    1. Firstly check the Platform Installation log file in the install folder. Check for any errors, which may have been caused during platform installation on your system, and then try to resolve them accordingly.
    2. Next check for nginx status by `service nginx status` command, if it is not active, check nginx error log file, possibly in `/var/log/nginx/error.log` file.
    3. Next check for platform status by `service platform status` command, if it is not `active(running)` then check for platform logs in the `logs` directory of your project.
    4. In case of any gunicorn error try manually running `/etc/init.d/platform start` command and recheck the platform status.

### Setting Up The Bucket
After the completion of the automated installation of the platform, the following folder structure is created in the 'SAMPLE_REPOSITORY' set during installation:
- `LogFiles/` - Directory containing log files of the tests completed
- `QueuedFiles/` - Directory containing files related to queued samples
- `README` - A readme file related to SSL certificates required by the platform
- `TempFiles/` - Directory containing temporary files
- `TestData/` - Directory containing files required for starting a test - runCI files, variables file, tester
- `TestFiles/` - Directory containing regression test samples
- `TestResults/` - Direction containing regression test results
- `vm_data/` - Directory containing test-specific subfolders, each folder containing files required for testing to be passed to the VM instance, test files and CCExtractor build artefact.

Now for tests to run, we need to download the [CCExtractor testsuite](https://github.com/CCExtractor/ccx_testsuite) release file, extract and put it in `TestData/ci-linux` and `TestData/ci-windows` folders.

## GCS configuration to serve file downloads using Signed URLs

To serve file downloads directly from the private GCS bucket, Signed download URLs have been used.

The `serve_file_download` function in the `utility.py` file implements the generation of a signed URL for the file to be downloaded that would expire after a configured time limit (maximum limit: 7 days) and redirects the client to the URL.

For more information about Signed URLs, you can refer to the [official documentation](https://cloud.google.com/storage/docs/access-control/signed-urls).


## File upload size for HTTP

In order to accept big files through HTTP uploads, some files need to be 
adapted.

### Nginx

If the upload is too large, Nginx will throw a 
`413 Request entity too large`. To remedy this error, modify the next section
in the nginx config:

```
# Increase Nginx upload limit
client_max_body_size 1G;
```

## Pure-FTPD configuration

Besides HTTP, there is also an option available to upload files through FTP.
As the privacy of individual sample submitters should be respected, each user
must get it's own FTP account. However, system accounts pose a possible 
security threat, so virtual accounts (using MySQL) are to be used instead. 
Virtual users also offer the added benefit of easier management.

### Pure-FTPD installation

`sudo apt-get install pure-ftpd-mysql`

If requested, answer the following questions as follows:

```
Run pure-ftpd from inetd or as a standalone server? <-- standalone
Do you want pure-ftpwho to be installed setuid root? <-- No
```

### Special group & user creation

All MySQL users will be mapped to this user. A group and user id that is
still available should be chosen.

```
sudo groupadd -g 2015 ftpgroup
sudo useradd -u 2015 -s /bin/false -d /bin/null -c "pureftpd user" -g ftpgroup ftpuser
```

### Configure Pure-FTPD

Edit the `/etc/pure-ftpd/db/mysql.conf` file (in case of Debian/Ubuntu) so it
matches the next configuration:

```
MYSQLSocket      /var/run/mysqld/mysqld.sock
# user from the DATABASE_USERNAME in the configuration, or a separate one
MYSQLUser       user 
# password from the DATABASE_PASSWORD in the configuration, or a separate one
MYSQLPassword   ftpdpass
# The database name configured in the DATABASE_SOURCE_NAME dsn string in the configuration
MYSQLDatabase   pureftpd
# For now we use plaintext. While this is terribly insecure in case of a database leakage, it's not really an issue, 
# given the fact that the passwords for the FTP accounts will be randomly generated and hence do not contain sensitive 
# user info (we need to show the password on the site after all).
MYSQLCrypt      plaintext
# Queries
MYSQLGetPW      SELECT password FROM ftpd WHERE user_name="\L" AND status="1" AND (ip_access = "*" OR ip_access LIKE "\R")
MYSQLGetUID     SELECT uid FROM ftpd WHERE user_name="\L" AND status="1" AND (ip_access = "*" OR ip_access LIKE "\R")
MYSQLGetGID     SELECT gid FROM ftpd WHERE user_name="\L" AND status="1" AND (ip_access = "*" OR ip_access LIKE "\R")
MYSQLGetDir     SELECT dir FROM ftpd WHERE user_name="\L" AND status="1" AND (ip_access = "*" OR ip_access LIKE "\R")
MySQLGetQTAFS   SELECT quota_files FROM ftpd WHERE user_name="\L" AND status="1" AND (ip_access = "*" OR ip_access LIKE "\R")
# Override queries for UID & GID
MYSQLDefaultUID 2015 # Set the UID of the ftpuser here
MYSQLDefaultGID 2015 # Set the GID of the ftpgroup here
```

Next, a file called `ChrootEveryone` must be created, so that the individual
users are jailed:

```
echo "yes" | sudo tee /etc/pure-ftpd/conf/ChrootEveryone
```

The same needs to be done for `CreateHomeDir` and `CallUploadScript`:

```
echo "yes" | sudo tee /etc/pure-ftpd/conf/CreateHomeDir
echo "yes" | sudo tee /etc/pure-ftpd/conf/CallUploadScript
```

Set `PassivePortRange` for pure-ftpd:
```
echo "30000 50000" | sudo tee /etc/pure-ftpd/conf/PassivePortRange
```

Also `/etc/default/pure-ftpd-common` needs some modification:

```
UPLOADSCRIPT=/path/to/cron/progress_ftp_upload.py
UPLOADUID=33 # User that owns the upload.sh script
UPLOADGID=33 # Group that owns the upload.sh script
```

You can get the UPLOADUID and UPLOADGID using the following command:
```
ls -l /path/to/cron/progress_ftp_upload.py
```

Since we provide bucket access only to group `www-data`, we will now add `ftpuser` to the group:
```
sudo usermod -a -G www-data ftpuser
```
In manual installation, you may change `www-data` to the group you provided the bucket access.

When necessary, an appropriate value in the Umask file 
(`/etc/pure-ftpd/conf/Umask`) should be set as well.

After this you Pure-FTPD can be restarted using 
`sudo /etc/init.d/pure-ftpd-mysql restart`

Note: if there is no output saying: 
`Restarting ftp upload handler: pure-uploadscript.`, the uploadscript will
need to be started. This can be done using the next command (assuming 33 is
the `gid` and `uid` of the user which was specified earlier):

```
sudo pure-uploadscript -u 33 -g 33 -B -r /home/path/to/src/cron/progress_ftp_upload.py
sudo chown 33:33 /home/path/to/src/cron/progress_ftp_upload.py
```

To check if the upload script is running, the next command can help:
`ps aux | grep pure-uploadscript`. If it still doesn't work, rebooting the 
server might help as well.

### Configure GCP Firewall for Pure-FTP
NOTE: These steps need to be performed only if the platform is being installed on a GCP VM instance.

Since pure-ftpd server runs over TCP port 21 and we allow passive TCP port range as 30000-50000, we should now allow incoming communication requests through these ports to the platform server:

- Navigate to VPC network -> Firewall and click on "Create Firewall Rule".
- Set the name as "default-allow-ftp-ingress" and enter the following details for this rule:
    - Priority: 1000
    - Direction of Traffic: Ingress
    - Action on the match: Allow
        - Target type: "Allow instances in the network"
        - Source Filter: IPv4 ranges
        - Source IPv4 ranges: 0.0.0.0/0
        - Protocols and ports -> Specified protocols and ports -> TCP -> Port: 21,30000-50000
    - Now click on "Save"

### Setup Automated Deployments for Platform via GitHub
To setup automated deployments via GitHub workflows, follow these steps:
- Ensure GitHub Actions is enabled in the repository (It is disabled for forks by default).
- Create two new GitHub repository variables, from the Settings tab
    - Navigate to "Secrets and variables" -> "Actions" -> "Variables".
    - Click on "New repository variable" and setup the following variables:
        - `PLATFORM_DOMAIN`: The domain your platform is to be deployed, for example: `sampleplatform.ccextractor.org`.
        - `SSH_USER`: The user that has root access and would be used to SSH into the server. 
        
            (You can see a list of users in your system by running the command ```less /etc/passwd```)

    - Now get the SSH private and public(`.pub`) keys by running the following command locally:
        ```
        ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
        ```
    - Now SSH into the VM instance where the platform is to be deployed, open the file `/home/<SSH_USER>/.ssh/authorized_keys` and append the contents of the public key to the end of the file.
    - Now the last step is to add the SSH private key to the GitHub secrets
        - Navigate to "Secrets and variables" -> "Actions" -> "Secrets".
        - Click on "New repository secret" and setup the following variable:
            - `SSH_KEY_PRIVATE`: Save the contents of the private SSH key file created in the last step as this secret.
    - Also checkout the variables `INSTALL_FOLDER` and `SAMPLE_REPOSITORY` in the [deployment pipeline](/.github/workflows/sp-deployment-pipeline.yml) in case you have configured values other than default.
    