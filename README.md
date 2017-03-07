# CCExtractor Sample Platform

This repository contains the code for a platform that manages a test suite bot, sample upload and more. This platform allows for a unified place to report errors, submit samples, view existing samples and more. It was originally developed during GSoC 2015 and rewritten during GSoC 2016.

You can find a running version here: [CCExtractor Submission Platform](https://sampleplatform.ccextractor.org/)

## Concept

While CCExtractor is an awesome tool and it works flawlessly most of the time, bugs occur occasionally (as with all existing software). These are usually reported through a variety of channels (private email, mailing list, GitHub, and so on...).

The aim of this project is to build a platform, which is accessible to everyone (after signing up), that provides a single place to upload, view samples and associated test results.

## Installation

### Requirements

* Nginx (Other possible when modifying the sample download section)
* Python 2.7 (Flask and other dependencies)
* MySQL
* Pure-FTPD with mysql

### Automated install

#### Linux

Clone the latest sample-platform repository from https://github.com/canihavesomecoffee/sample-platform.
```
git clone https://github.com/canihavesomecoffee/sample-platform.git
```
The `sample-repository` directory needs to be accessible by www-data.

Recommended directory :`/var/www/`

Navigate to the `install` folder and run `install.sh` as root.
```
cd sample-platform/install/
sudo ./install.sh
```    
Installer script will begin downloading and updating all the necessary dependecies. Once done, it'll prompt you for some details for setting up the sample-platform.

Simply answer all the questions in required format and sample-platform will be ready to use.

Please read the below troubleshooting notes in case of any error or doubt.

#### Troubleshooting

1. Both installation and running the platform requires root (or sudo).

2. The configuration of the sample platform assumes that no other application already runs on port 80. A default installation of nginx leaves a `default` config file behind, so it's advised to delete that and stop other applications that use the port.

    Note : Do not forget to do `service nginx reload` and `service platform start` after making the changes.

3. SSL is a requirement. If you are running this on a live server, you may use Let's Encrypt for the certificates. If you run it locally, you may use self-signed certificates.

4. When prompted for server name, enter the domain name you wish to run it upon. If you are trying to run it locally, enter `localhost` as the server name.

5. If you get a `502 Bad Gateway` response, the platform wasn't started correctly. You may manually run (as root!) `bootstrap_gunicorn.py` to determine what goes wrong.

   ```
   cd /var/www/sample-platform/
   sudo python bootstrap_gunicorn.py
   ```
6. If `gunicorn` boots up successfully, most relevant logs would be stored under `logs` directory, otherwise you may have to read `syslog`.

### Nginx configuration for X-Accel-Redirect

To serve files without any PHP overhead, the X-Accel-Redirect feature of Nginx is used. To enable it, a special section (as seen below) needs to be added to the nginx configuration file:

```
location /protected/ {
    internal;
    alias /path/to/storage/of/samples/; # Trailing slash is important!
}
```

More info on this directive is available at the [Nginx wiki](http://wiki.nginx.org/NginxXSendfile).

Other web servers can be configured too (see this excellent [SO](http://stackoverflow.com/a/3731639) answer), but will require a small modification in the relevant section of the SampleInfoController that handles the download.

### File upload size for HTTP

There are a couple of places where you need to take care to set a big enough size (depending on your wishes) when you want to set/increase the upload limit for HTTP uploads.

#### Nginx

If the upload is too large, Nginx will throw a `413 Request entity too large`. This can be solved by adding

```
# Increase Nginx upload limit
client_max_body_size 1G;
```

And setting it to an appropriate limit.

### Pure-FTPD configuration

To allow upload of big files, FTP can be used. Since the goal is to keep the uploaded files of the users anonymous for other users, every user should get it's own FTP account.

Since system accounts pose a possible security threat, virtual accounts using MySQL can be used instead (and it's easier to manage too).

#### Pure-FTPD installation

`sudo apt-get install pure-ftpd-mysql`

If requested, answer the following questions as follows:

```
Run pure-ftpd from inetd or as a standalone server? <-- standalone
Do you want pure-ftpwho to be installed setuid root? <-- No
```

#### Special group & user creation

All MySQL users will be mapped to this user. Pick a group and user id that is still free

```
sudo groupadd -g 2015 ftpgroup
sudo useradd -u 2015 -s /bin/false -d /bin/null -c "pureftpd user" -g ftpgroup ftpuser
```

#### Configure Pure-FTPD

Edit the `/etc/pure-ftpd/db/mysql.conf` file (in case of Debian/Ubuntu) so it matches the next configuration:

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
MYSQLGetPW      SELECT Password FROM ftpd WHERE User="\L" AND status="1" AND (ipaccess = "*" OR ipaccess LIKE "\R")
MYSQLGetUID     SELECT Uid FROM ftpd WHERE User="\L" AND status="1" AND (ipaccess = "*" OR ipaccess LIKE "\R")
MYSQLGetGID     SELECT Gid FROM ftpd WHERE User="\L" AND status="1" AND (ipaccess = "*" OR ipaccess LIKE "\R")
MYSQLGetDir     SELECT Dir FROM ftpd WHERE User="\L" AND status="1" AND (ipaccess = "*" OR ipaccess LIKE "\R")
MySQLGetQTAFS   SELECT QuotaFiles FROM ftpd WHERE User="\L" AND status="1" AND (ipaccess = "*" OR ipaccess LIKE "\R")
# Override queries for UID & GID
MYSQLDefaultUID 2015 # Set the UID of the ftpuser here
MYSQLDefaultGID 2015 # Set the GID of the ftpgroup here
```

Create a file `/etc/pure-ftpd/conf/ChrootEveryone` with the following contents:

```
yes
```

And do the same for `/etc/pure-ftpd/conf/CreateHomeDir` and `/etc/pure-ftpd/conf/CallUploadScript`

Then modify the `/etc/default/pure-ftpd-common`, and configure the next values:

```
UPLOADSCRIPT=/path/to/cron/upload.sh
UPLOADUID=1234 # User that owns the upload.sh script
UPLOADGID=1234 # Group that owns the upload.sh script
```

If necessary, you can also set an appropriate value in the Umask file (`/etc/pure-ftpd/conf/Umask`).

After this you can restart Pure-FTPD with `sudo /etc/init.d/pure-ftpd-mysql restart`

Note: if you don't see a line saying: `Restarting ftp upload handler: pure-uploadscript.`

You need to start the pure-uploadscript. This can be done as follows (where 1000 is replaced with the gid & uid specified above):

`sudo pure-uploadscript -u 1000 -g 1000 -B -r /home/path/to/src/cron/upload.sh`

You can also verify this by running `ps aux | grep pure-uploadscript`. If it still doesn't work, rebooting the server might help.

## Contributing

All information with regards to contributing can be found here: [contributors guide](https://github.com/canihavesomecoffee/sample-platform/blob/master/.github/CONTRIBUTING.md).

## Security

Security is taken seriously, but even though many precautions have been taken, bugs always can occur. If you discover any security related issues, please send an email to ccextractor@canihavesome.coffee (GPG key [0xF8643F5B](http://pgp.mit.edu/pks/lookup?op=vindex&search=0x3AFDC9BFF8643F5B), fingerprint 53FF DE55 6DFC 27C3 C688 1A49 3AFD C9BF F864 3F5B) instead of using the issue tracker, in order to prevent abuse while it's being patched.
