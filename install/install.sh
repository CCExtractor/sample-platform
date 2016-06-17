#!/bin/bash
#
# Installer for the CCExtractor sample platform
#
# More information can be found on:
# https://github.com/canihavesomecoffee/sample-platform
#
dir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
root_dir=$( cd "${dir}"/../ && pwd)
clear
date=`date +%Y-%m-%d`
install_log="${dir}/PlatformInstall_${date}_log.txt"
echo "Welcome to the CCExtractor platform installer!"
echo ""
echo "Detailed information will be written to $install_log"
echo ""
echo "-------------------------------"
echo "|   Installing dependencies   |"
echo "-------------------------------"
echo ""
echo "* Updating package list        "
apt-get update >> "$install_log" 2>&1
echo "* Installing nginx, python & pip      "
apt-get -q -y install nginx python python-dev python-pip >> "$install_log" 2>&1
if [ ! -f /etc/init.d/mysql* ]; then
    echo "* Installing MySQL (root password will be empty!)"
    DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server >> "$install_log" 2>&1
fi
echo "* Update setuptools            "
easy_install -U setuptools >> "$install_log" 2>&1
echo "* Installing pip dependencies"
pip install sqlalchemy flask passlib pymysql flask-wtf gunicorn githubpy requests pyIsEmail >> "$install_log" 2>&1
echo ""
echo "-------------------------------"
echo "|        Configuration        |"
echo "-------------------------------"
echo ""
echo "In order to configure the platform, we need some information from you. Please reply to the next questions:"
echo ""
read -e -p "Password of the 'root' user of MySQL: " -i "" db_root_password
# Verify password
while ! mysql -u root --password="${db_root_password}"  -e ";" ; do
       read -e -p "Invalid password, please retry: " -i "" db_root_password
done
read -e -p "Database name for storing data: " -i "sample_platform" db_name
mysql -u root --password="${db_root_password}" -e "CREATE DATABASE IF NOT EXISTS ${db_name};" >> "$install_log" 2>&1
# Check if DB exists
db_exists=`mysql -u root --password="${db_root_password}" -se"USE ${db_name};" 2>&1`
if [ ! "${db_exists}" == "" ]; then
    echo "Failed to create the database! Please check the installation log!"
    exit -1
fi
read -e -p "Username to connect to ${db_name}: " -i "sample_platform" db_user
# Check if user exists
db_user_exists=`mysql -u root --password="${db_root_password}" -sse "SELECT EXISTS(SELECT 1 FROM mysql.user WHERE user = '${db_user}')"`
db_user_password=""
if [ ${db_user_exists} = 0 ]; then
    rand_pass=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 16 | head -n 1)
    read -e -p "Password for ${db_user} (will be created): " -i "${rand_pass}" db_user_password
    # Attempt to create the user
    mysql -u root --password="$db_root_password" -e "CREATE USER '${db_user}'@'localhost' IDENTIFIED BY '${db_user_password}';" >> "$install_log" 2>&1
    db_user_exists=`mysql -u root --password="$db_root_password" -sse "SELECT EXISTS(SELECT 1 FROM mysql.user WHERE user = '$db_user')"`
    if [ ${db_user_exists} = 0 ]; then
        echo "Failed to create the user! Please check the installation log!"
        exit -1
    fi
else
    read -e -p "Password for ${db_user}: " db_user_password
    # Check if we have access
    while ! mysql -u "${db_user}" --password="${db_user_password}"  -e ";" ; do
       read -e -p "Invalid password, please retry: " -i "" db_user_password
    done
fi
# Grant user access to database
mysql -u root --password="${db_root_password}" -e "GRANT ALL ON ${db_name}.* TO '${db_user}'@'localhost';" >> "$install_log" 2>&1
# Check if user has access
db_access=`mysql -u "${db_user}" --password="${db_user_password}" -se"USE ${db_name};" 2>&1`
if [ ! "${db_access}" == "" ]; then
    echo "Failed to grant user access to database! Please check the installation log!"
    exit -1
fi
# Request information for generating the config.py file
read -e -p "(Sub)domain this will be running on? " -i "" config_server_name
read -e -p "Application root (if not a whole (sub)domain, enter the path. None if whole (sub)domain): " -i "None" config_application_root
read -e -p "Path to SSL certificate: " -i "/etc/letsencrypt/live/${config_server_name}/fullchain.pem" config_ssl_cert
read -e -p "Path to SSL key: " -i "/etc/letsencrypt/live/${config_server_name}/privkey.pem" config_ssl_key
config_db_uri="mysql+pymysql://${db_user}:${db_user_password}@localhost:3306/${db_name}"
# TODO: update for new config variables
# Request info for creating admin account
echo ""
echo "We need some information for the admin account"
read -e -p "Admin username: " -i "admin" admin_name
read -e -p "Admin email: " admin_email
read -e -p "Admin password: " admin_password
echo "Creating admin account: "
python "${dir}/init_db.py" "${config_db_uri}" "${admin_name}" "${admin_email}" "${admin_password}"
echo ""
echo "-------------------------------"
echo "|      Finalizing install     |"
echo "-------------------------------"
echo ""
echo "* Generating secret keys"
# Write two secret keys (1 for session, 1 for CSRF)
head -c 24 /dev/urandom > "${dir}/../secret_key"
head -c 24 /dev/urandom > "${dir}/../secret_csrf"
# Write config file
echo "* Generating config file"
echo "# Auto-generated configuration by install.sh
APPLICATION_ROOT = ${config_application_root}
CSRF_ENABLED = True
DATABASE_URI = '${config_db_uri}'
" > "${dir}/../config.py"
# Ensure the files are executable by www-data
chown www-data:www-data "${root_dir}/secret_key" "${root_dir}/secret_csrf" "${root_dir}/config.py"
echo "* Creating startup script"
cp "${dir}/platform" /etc/init.d/platform >> "$install_log" 2>&1
sed -i "s#BASE_DIR#${root_dir}#g" /etc/init.d/platform >> "$install_log" 2>&1
chmod 755 /etc/init.d/platform >> "$install_log" 2>&1
update-rc.d platform defaults >> "$install_log" 2>&1
echo "* Creating Nginx config"
cp "${dir}/nginx.conf" /etc/nginx/sites-available/platform >> "$install_log" 2>&1
sed -i "s/NGINX_HOST/${config_server_name}/g" /etc/nginx/sites-available/platform >> "$install_log" 2>&1
sed -i "s#NGINX_CERT#${config_ssl_cert}#g" /etc/nginx/sites-available/platform >> "$install_log" 2>&1
sed -i "s#NGINX_KEY#${config_ssl_key}#g" /etc/nginx/sites-available/platform >> "$install_log" 2>&1
sed -i "s#NGINX_DIR#${root_dir}#g" /etc/nginx/sites-available/platform >> "$install_log" 2>&1
ln -s /etc/nginx/sites-available/platform /etc/nginx/sites-enabled/platform >> "$install_log" 2>&1
echo "* Reloading nginx"
service nginx reload >> "$install_log" 2>&1
echo ""
echo "* Starting Platform..."
service platform start
echo "Platform installed!"