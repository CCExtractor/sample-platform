#!/bin/bash
#
# Installer for the CCExtractor sample platform
#
# More information can be found on:
# https://github.com/CCExtractor/sample-platform
#
dir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
root_dir=$( cd "${dir}"/../ && pwd)
clear
date=`date +%Y-%m-%d-%H-%M`
install_log="${dir}/PlatformInstall_${date}_log.txt"
echo "Welcome to the CCExtractor platform installer!"
if [[ $EUID -ne 0 ]]
    then
        echo "You must be a root user to install CCExtractor platform." 2>&1
        exit -1
fi
echo ""
echo "Detailed information will be written to $install_log"
echo "Please read the installation instructions carefully before installing."
echo ""
echo "-------------------------------"
echo "|   Installing dependencies   |"
echo "-------------------------------"
echo ""
echo "* Updating package list"
apt-get update >> "$install_log" 2>&1
echo "* Installing nginx, python, pip, kvm, libvirt and virt-manager"
apt-get -q -y install nginx python python-dev python3-libvirt libxslt1-dev libxml2-dev python-pip qemu-kvm libvirt-bin virt-manager mediainfo >> "$install_log" 2>&1
if [ ! -f /etc/init.d/mysql* ]; then
    echo "* Installing MySQL (root password will be empty!)"
    DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server >> "$install_log" 2>&1
fi
echo "* Update pip, setuptools and wheel"
python -m pip install --upgrade pip setuptools wheel >> "$install_log" 2>&1
echo "* Installing pip dependencies"
pip install -r "${root_dir}/requirements.txt" >> "$install_log" 2>&1
echo ""
echo "-------------------------------"
echo "|        Configuration        |"
echo "-------------------------------"
echo ""
echo "In order to configure the platform, we need some information from you. Please reply to the following questions:"
echo ""
read -e -p "Password of the 'root' user of MySQL: " -i "" db_root_password
# Verify password
supress_warning=`mysql_config_editor set --login-path=root_login --host=localhost --user=root --password ${db_root_password}` >> "$install_log" 2>&1
while ! mysql  --login-path=root_login  -e ";" ; do
      read -e -p "Invalid password, please retry: " -i "" db_root_password
      supress_warning=`mysql_config_editor set --login-path=root_login --host=localhost --user=root --password ${db_root_password}` >> "$install_log" 2>&1
done


read -e -p "Database name for storing data: " -i "sample_platform" db_name
mysql -u root --password="${db_root_password}" -e "CREATE DATABASE IF NOT EXISTS ${db_name};" >> "$install_log" 2>&1
# Check if DB exists
db_exists=`mysql --login-path=root_login -se"USE ${db_name};" 2>&1`
if [ ! "${db_exists}" == "" ]; then
    echo "Failed to create the database! Please check the installation log!"
    exit -1
fi
read -e -p "Username to connect to ${db_name}: " -i "sample_platform" db_user
# Check if user exists
db_user_exists=`mysql --login-path=root_login -sse "SELECT EXISTS(SELECT 1 FROM mysql.user WHERE user = '${db_user}')"`

if [ ${db_user_exists} = 0 ]; then
    rand_pass=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 16 | head -n 1)
    read -e -p "Password for ${db_user} (will be created): " -i "${rand_pass}" db_user_password
    # Attempt to create the user
    mysql --login-path=root_login -e "CREATE USER '${db_user}'@'localhost' IDENTIFIED BY '${db_user_password}';" >> "$install_log" 2>&1
    db_user_exists=`mysql --login-path=root_login -sse "SELECT EXISTS(SELECT 1 FROM mysql.user WHERE user = '$db_user')"`
    if [ ${db_user_exists} = 0 ]; then
        echo "Failed to create the user! Please check the installation log!"
        exit -1
    fi
else
    read -e -p "Password for ${db_user}: " db_user_password
    supress_warning=`mysql_config_editor set --login-path=check_login --host=localhost --user=${db_user} --password ${db_root_password}` >> "$install_log" 2>&1
    # Check if we have access
    while ! mysql  --login-path=check_login  -e ";" ; do
       read -e -p "Invalid password, please retry: " -i "" db_user_password
       supress_warning=`mysql_config_editor set --login-path=check_login --host=localhost --user=${db_user} --password ${db_root_password}` >> "$install_log" 2>&1
    done
fi
supress_warning=`mysql_config_editor set --login-path=user_login --host=localhost --user=${db_user} --password ${db_user_password}` >> "$install_log" 2>&1
# Grant user access to database
mysql --login-path=root_login -e "GRANT ALL ON ${db_name}.* TO '${db_user}'@localhost;" >> "$install_log" 2>&1
# Check if user has access
db_access=`mysql --login-path=user_login -se "USE ${db_name};" 2>&1`
if [ ! "${db_access}" == "" ]; then
    echo "Failed to grant user access to database! Please check the installation log!"
    exit -1
fi
read -p "Do you want to install a sample database? (y/n) :" sample_response
# Request information for generating the config.py file
echo ""
echo "For the following questions, press enter to leave a field blank."
read -e -p "(Sub)domain this will be running on? " -i "" config_server_name
read -e -p "Application root (if not a whole (sub)domain, enter the path. None if whole (sub)domain): " -i "None" config_application_root
read -e -p "Github Token (Generate here : https://help.github.com/articles/creating-an-access-token-for-command-line-use/): " -i "" github_token
read -e -p "Github Owner Name : " -i "CCExtractor" github_owner_name
read -e -p "Github repository : " -i "ccextractor" github_repository
read -e -p "Email Domain : " -i "${config_server_name}" email_domain
read -e -p "Email API key (Generate one here https://www.mailgun.com/) : " -i "" email_api_key
hmac_key=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)
read -e -p "Github Automated Deploy Webhook Secret (More info : https://developer.github.com/webhooks/) : " -i "" github_deploy_key
read -e -p "Github CI Webhook Secret (More info: https://developer.github.com/webhooks/) : " -i "" github_ci_key
read -e -p "KVM Linux Name: " -i "" kvm_linux_name
read -e -p "KVM Windows Name: " -i "" kvm_windows_name
read -e -p "KVM Max Runtime (In minutes): " -i "120" kvm_max_runtime
read -e -p "FTP Server IP/Domain name :" -i "" server_name
read -e -p "FTP port: " -i "21" ftp_port
read -e -p "Max HTTP sample size (in bytes) : " -i "536870912" max_content_length
read -e -p "Minimum password length : " -i "10" min_pwd_len
read -e -p "Maximum password length : " -i "500" max_pwd_len


echo ""
echo "In the following lines, enter the path "
read -e -p "    To SSL certificate: " -i "/etc/letsencrypt/live/${config_server_name}/fullchain.pem" config_ssl_cert
read -e -p "    To SSL key: " -i "/etc/letsencrypt/live/${config_server_name}/privkey.pem" config_ssl_key
read -e -p "    To the root directory containing all files (Samples, reports etc.) : " -i "/repository" sample_repository

echo "Setting up the directories.."

mkdir -p "${sample_repository}" >> "$install_log" 2>&1
mkdir -p "${sample_repository}/ci-tests" >> "$install_log" 2>&1
mkdir -p "${sample_repository}/unsafe-ccextractor" >> "$install_log" 2>&1
mkdir -p "${sample_repository}/TempFiles" >> "$install_log" 2>&1
mkdir -p "${sample_repository}/LogFiles" >> "$install_log" 2>&1
mkdir -p "${sample_repository}/TestResults" >> "$install_log" 2>&1
mkdir -p "${sample_repository}/TestFiles" >> "$install_log" 2>&1
mkdir -p "${sample_repository}/TestFiles/media" >> "$install_log" 2>&1
mkdir -p "${sample_repository}/QueuedFiles" >> "$install_log" 2>&1

config_db_uri="mysql+pymysql://${db_user}:${db_user_password}@localhost:3306/${db_name}"
# Request info for creating admin account
echo ""
echo "We need some information for the admin account"
read -e -p "Admin username: " -i "admin" admin_name
read -e -p "Admin email: " admin_email
read -e -p "Admin password: " admin_password
echo "Creating admin account: "
python "${dir}/init_db.py" "${config_db_uri}" "${admin_name}" "${admin_email}" "${admin_password}"
# Create sample database if user wanted to
if [ ${sample_response} == 'y' ]; then
  echo "Creating sample database.."
  cp -r sample_files/* "${sample_repository}/TestFiles"
  python "${dir}/sample_db.py" ${config_db_uri}
fi
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
DATABASE_URI = '${config_db_uri}?charset=utf8'
GITHUB_TOKEN = '${github_token}'
GITHUB_OWNER = '${github_owner_name}'
GITHUB_REPOSITORY = '${github_repository}'
SERVER_NAME = '${server_name}'
EMAIL_DOMAIN = '${email_domain}'
EMAIL_API_KEY = '${email_api_key}'
HMAC_KEY = '${hmac_key}'
GITHUB_DEPLOY_KEY = '${github_deploy_key}'
GITHUB_CI_KEY = '${github_ci_key}'
INSTALL_FOLDER = '${root_dir}'
KVM_LINUX_NAME = '${kvm_linux_name}'
KVM_WINDOWS_NAME = '${kvm_windows_name}'
KVM_MAX_RUNTIME = $kvm_max_runtime # In minutes
SAMPLE_REPOSITORY = '${sample_repository}'
SESSION_COOKIE_PATH = '/'
FTP_PORT = $ftp_port
MAX_CONTENT_LENGTH = $max_content_length
MIN_PWD_LEN = $min_pwd_len
MAX_PWD_LEN = $max_pwd_len
" > "${dir}/../config.py"
# Ensure the files are executable by www-data
chown -R www-data:www-data "${root_dir}" "${sample_repository}"
echo "* Creating startup script"
cp "${dir}/platform" /etc/init.d/platform >> "$install_log" 2>&1
sed -i "s#BASE_DIR#${root_dir}#g" /etc/init.d/platform >> "$install_log" 2>&1
chmod 755 /etc/init.d/platform >> "$install_log" 2>&1
update-rc.d platform defaults >> "$install_log" 2>&1
echo "* Creating Nginx config"

cp "${dir}/nginx.conf" /etc/nginx/sites-available/platform >> "$install_log" 2>&1
sed -i "s/NGINX_HOST/${config_server_name}/g" /etc/nginx/sites-available/platform >> "$install_log" 2>&1
sed -i "s#SAMPLE_DIR#${sample_repository}/TestFiles/media#g" /etc/nginx/sites-available/platform >> "$install_log" 2>&1
sed -i "s#LOGFILE_DIR#${sample_repository}/LogFiles#g" /etc/nginx/sites-available/platform >> "$install_log" 2>&1
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
