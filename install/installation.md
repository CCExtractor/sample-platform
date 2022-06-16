# Installation

## Requirements

* Nginx (Other possible when modifying the sample download section)
* Python 3 (Flask and other dependencies)
* MySQL
* Pure-FTPD with mysql

## Automated install

Automated install only works for the platform section, **not** for the KVM
functionality. To install the VM's for KVM, see 
[the installation guide](ci-vm/installation.md).

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

Next, navigate to the `install` folder and run `install.sh` with root 
permissions.

```
cd sample-platform/install/
sudo ./install.sh
```    

The `install.sh` will begin downloading and updating all the necessary 
dependencies. Once done, it'll ask to enter some details in order to set up 
the sample-platform. After filling in these the platform should be ready for
use.

Please read the below troubleshooting notes in case of any error or doubt.

### Windows

* Install cygwin (http://cygwin.com/install.html). When cygwin asks which
 packages to install, select Python, MySql, virt-manager and openssh. If you 
 already have cygwin installed, you must run its setup file to install the new packages. Make sure the dropdown menu is set to Full, so you can all packages. To select one, click skip and it will change to the version number of the package. Use the end of [this](https://www.davidbaumgold.com/tutorials/set-up-python-windows/) tutorial for help on getting cygwin to recognize python. 
* Start a terminal session once installation is complete. 
* Install Nginx (see http://nginx.org/en/docs/windows.html)
* Install XMing XServer and setup Putty for ssh connections.
* Virt-manager can call ssh to make the connection to KVM Server and should be 
able to run virsh and send commands to it. 
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

* If it shows the error regarding the `libvirt`, then there is missing `fftw3.h` file. Try the following:
```
sudo apt-get install libvirt-dev
sudo apt-get install libfftw3-dev
sudo apt-get install libsndfile1-dev
```

* If any issue still persists, follow the mentioned steps to debug and troubleshoot your issue:
    1. Firstly check the Platform Installation log file in the install folder. Check for any errors, which may have been caused during platform installation on your system, and then try to resolve them accordingly.
    2. Next check for nginx status by `service nginx status` command, if it is not active, check nginx error log file, possibly in `/var/log/nginx/error.log` file.
    3. Next check for platform status by `service platform status` command, if it is not `active(running)` then check for platform logs in the `logs` directory of your project.
    4. In case of any gunicorn error try manually running `/etc/init.d/platform start` command and recheck the platform status.

## Nginx configuration for X-Accel-Redirect

To serve files without any scripting language overhead, the X-Accel-Redirect 
feature of Nginx is used. To enable it, a special section (as seen below) 
needs to be added to the nginx configuration file:

```
location /protected/ {
    internal;
    alias /path/to/storage/of/samples/; # Trailing slash is important!
}
```

More info on this directive is available at the 
[Nginx wiki](http://wiki.nginx.org/NginxXSendfile).

Other web servers can be configured too (see this excellent 
[SO](http://stackoverflow.com/a/3731639) answer), but will require a small 
modification in the relevant section of the `serve_file_download` definition 
in `mod_sample/controllers.py` which is responsible for handling the download
requests.

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
echo "yes" > /etc/pure-ftpd/conf/ChrootEveryone
```

The same needs to be done for `CreateHomeDir` and `CallUploadScript`:

```
echo "yes" > /etc/pure-ftpd/conf/CreateHomeDir
echo "yes" > /etc/pure-ftpd/conf/CallUploadScript
```

Also `/etc/default/pure-ftpd-common` needs some modification:

```
UPLOADSCRIPT=/path/to/cron/progress_ftp_upload.py
UPLOADUID=2015 # User that owns the upload.sh script
UPLOADGID=2015 # Group that owns the upload.sh script
```

When necessary, an appropriate value in the Umask file 
(`/etc/pure-ftpd/conf/Umask`) should be set as well.

After this you Pure-FTPD can be restarted using 
`sudo /etc/init.d/pure-ftpd-mysql restart`

Note: if there is no output saying: 
`Restarting ftp upload handler: pure-uploadscript.`, the uploadscript will
need to be started. This can be done using the next command (assuming 1000 is
the `gid` and `uid` of the user which was specified earlier):

```
sudo pure-uploadscript -u 2015 -g 2015 -B -r /home/path/to/src/cron/progress_ftp_upload.py
sudo chown 2015:2015 /home/path/to/src/cron/progress_ftp_upload.py

```

To check if the upload script is running, the next command can help:
`ps aux | grep pure-uploadscript`. If it still doesn't work, rebooting the 
server might help as well.
