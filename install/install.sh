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
date=$(date +%Y-%m-%d-%H-%M)
install_log="${dir}/PlatformInstall_${date}_log.txt"
echo "Welcome to the CCExtractor platform installer!"
if [[ "$EUID" -ne 0 ]]
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
echo "* Installing nginx, python, pip, mediainfo and gunicorn"
apt-get -q -y install nginx python3 python-is-python3 python3-pip mediainfo gunicorn3 >> "$install_log" 2>&1
rm -f /etc/nginx/sites-available/default
rm -f /etc/nginx/sites-enabled/default
for file in /etc/init.d/mysql*
do
    if [ ! -f "$file" ]; then
        mysql_user_resp="Y"
        while [ "$mysql_user_resp" != "N" ]; do
            echo "* Installing MySQL (root password will be empty!)"
            apt-get install -y mysql-server >> "$install_log" 2>&1
            if [ $? -ne 0 ]; then
                read -e -r -p "MySQL installation failed! Do you want to try again? [Y for yes | N for No | Q to quit installation] " -i "Y" mysql_user_resp
                if [ "$mysql_user_resp" = "Q" ]; then
                    exit 1
                fi
            fi
            if [  -f "$file" ]; then
                break
            fi
        done
    fi
done
echo "* Update pip, setuptools and wheel"
python -m pip install --upgrade pip setuptools wheel >> "$install_log" 2>&1
echo "* Installing pip dependencies"
python -m pip install -r "${root_dir}/requirements.txt" >> "$install_log" 2>&1
echo ""
echo "-------------------------------"
echo "|        Configuration        |"
echo "-------------------------------"
echo ""
echo "In order to configure the platform, we need some information from you. Please reply to the following questions:"
echo ""
read -s -e -r -p  "Password of the 'root' user of MySQL: " -i "" db_root_password
echo ""
# Verify password

supress_warning=$(mysql_config_editor set --login-path=root_login --host=localhost --user=root --password "${db_root_password}") >> "$install_log" 2>&1
while ! mysql  --login-path=root_login  -e ";" ; do
    read -s -e -r -p "Invalid password, please retry: " -i "" db_root_password
    echo "" 
    supress_warning=$(mysql_config_editor set --login-path=root_login --host=localhost --user=root --password "${db_root_password}") >> "$install_log" 2>&1
done


read -e -r -p "Database name for storing data: " -i "sample_platform" db_name
mysql -u root --password="${db_root_password}" -e "CREATE DATABASE IF NOT EXISTS ${db_name};" >> "$install_log" 2>&1
# Check if DB exists
db_exists=$(mysql --login-path=root_login -se"USE ${db_name};" 2>&1)
if [ ! "${db_exists}" == "" ]; then
    echo "Failed to create the database! Please check the installation log!"
    exit -1
fi
read -e -r -p "Username to connect to ${db_name}: " -i "sample_platform" db_user
# Check if user exists
db_user_exists=$(mysql --login-path=root_login -sse "SELECT EXISTS(SELECT 1 FROM mysql.user WHERE user = '${db_user}')")

if [ "${db_user_exists}" = 0 ]; then
    rand_pass=$(< /dev/urandom tr -dc 'a-zA-Z0-9' | fold -w 16 | head -n 1)
    read -e -r -p "Password for ${db_user} (will be created): " -i "${rand_pass}" db_user_password
    # Attempt to create the user
    mysql --login-path=root_login -e "CREATE USER '${db_user}'@'localhost' IDENTIFIED BY '${db_user_password}';" >> "$install_log" 2>&1
    db_user_exists=$(mysql --login-path=root_login -sse "SELECT EXISTS(SELECT 1 FROM mysql.user WHERE user = '$db_user')")
    if [ "${db_user_exists}" = 0 ]; then
        echo "Failed to create the user! Please check the installation log!"
        exit -1
    fi
else
    read -s -e -r -p "Password for ${db_user}: " db_user_password
    supress_warning=$(mysql_config_editor set --login-path=check_login --host=localhost --user="${db_user}" --password "${db_root_password}") >> "$install_log" 2>&1
    # Check if we have access
    while ! mysql  --login-path=check_login  -e ";" ; do
       read -s -e -r -p "Invalid password, please retry: " -i "" db_user_password
       supress_warning=$(mysql_config_editor set --login-path=check_login --host=localhost --user="${db_user}" --password "${db_root_password}") >> "$install_log" 2>&1
    done
fi
supress_warning=$(mysql_config_editor set --login-path=user_login --host=localhost --user="${db_user}" --password "${db_user_password}") >> "$install_log" 2>&1
# Grant user access to database
mysql --login-path=root_login -e "GRANT ALL ON ${db_name}.* TO '${db_user}'@localhost;" >> "$install_log" 2>&1
# Check if user has access
db_access=$(mysql --login-path=user_login -se "USE ${db_name};" 2>&1)
if [ ! "${db_access}" == "" ]; then
    echo "Failed to grant user access to database! Please check the installation log!"
    exit -1
fi
read -r -p "Do you want to install a sample database? (y/n) :" sample_response
# Request information for generating the config.py file
echo ""
echo "For the following questions, press enter to leave a field blank."
read -e -r -p "(Sub)domain this will be running on? " -i "" config_server_name
read -e -r -p "Application root (if not a whole (sub)domain, enter the path. None if whole (sub)domain): " -i "None" config_application_root
read -e -r -p "GitHub Token (Generate here : https://help.github.com/articles/creating-an-access-token-for-command-line-use/): " -i "" github_token
read -e -r -p "GitHub Owner Name : " -i "CCExtractor" github_owner_name
read -e -r -p "GitHub repository : " -i "ccextractor" github_repository
read -e -r -p "Email Domain : " -i "${config_server_name}" email_domain
read -e -r -p "Email API key (Generate one here https://www.mailgun.com/) : " -i "" email_api_key
hmac_key=$(head -80 /dev/urandom | LC_ALL=c tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)
read -e -r -p "GitHub Automated Deploy Webhook Secret (More info : https://developer.github.com/webhooks/) : " -i "" github_deploy_key
read -e -r -p "GitHub CI Webhook Secret (More info: https://developer.github.com/webhooks/) : " -i "" github_ci_key
read -e -r -p "FTP Server IP/Domain name :" -i "" server_name
read -e -r -p "FTP port: " -i "21" ftp_port
read -e -r -p "Max HTTP sample size (in bytes) : " -i "536870912" max_content_length
read -e -r -p "Minimum password length : " -i "10" min_pwd_len
read -e -r -p "Maximum password length : " -i "500" max_pwd_len

read -e -r -p "GCP service account file name (to be placed at root of project): " -i "service-account.json" gcp_service_account_file
read -e -r -p "GCP Project Name for the platform: " -i "" sample_platform_project_name
read -e -r -p "GCP Project Number for the platform: " -i "" sample_platform_project_number
read -e -r -p "Zone name for GCP Instances: " -i "us-west4-b" gcp_instance_zone_name
read -e -r -p "Machine type for GCP Instances: " -i "n1-standard-1" gcp_instance_machine_type
read -e -r -p "Windows GCP instance project name: " -i "windows-cloud" windows_instance_project_name
read -e -r -p "Windows GCP instance family name: " -i "windows-2019" windows_instance_family_name 
read -e -r -p "Linux GCP instance project name: " -i "ubuntu-os-cloud" linux_instance_project_name
read -e -r -p "Linux GCP instance family name: " -i "ubuntu-minimal-2204-lts" linux_instance_family_name
read -e -r -p "GCP Instance Max Runtime (In minutes): " -i "120" gcp_instance_max_runtime
read -e -r -p "Google Cloud Storage bucket name: " -i "" gcs_bucket_name
read -e -r -p "Google Cloud Storage bucket location: " -i "" gcs_bucket_location
read -e -r -p "Google Cloud Storage bucket location type: " -i "" gcs_bucket_location_type
read -e -r -p "Signed Download URLs expiry time (In minutes): " -i "720" signed_url_expiry_time


echo ""
echo "In the following lines, enter the path "
read -e -r -p "    To SSL certificate: " -i "/etc/letsencrypt/live/${config_server_name}/fullchain.pem" config_ssl_cert
read -e -r -p "    To SSL key: " -i "/etc/letsencrypt/live/${config_server_name}/privkey.pem" config_ssl_key
read -e -r -p "    To the root directory containing all files (Samples, reports etc.) : " -i "/repository" sample_repository

echo "Setting up the directories.."

{
    mkdir -p "${sample_repository}" 
    mkdir -p "${sample_repository}/ci-tests" 
    mkdir -p "${sample_repository}/unsafe-ccextractor"
    mkdir -p "${sample_repository}/TempFiles"
    mkdir -p "${sample_repository}/LogFiles"
    mkdir -p "${sample_repository}/TestResults"
    mkdir -p "${sample_repository}/TestFiles"
    mkdir -p "${sample_repository}/TestFiles/media"
    mkdir -p "${sample_repository}/QueuedFiles"
    mkdir -p "${sample_repository}/TestData/ci-linux"
    mkdir -p "${sample_repository}/TestData/ci-windows"
} >> "$install_log" 2>&1

config_db_uri="mysql+pymysql://${db_user}:${db_user_password}@localhost:3306/${db_name}"
# Request info for creating admin account
echo ""
echo "We need some information for the admin account"
read -e -r -p "Admin username: " -i "admin" admin_name

while [ -z $admin_email ];do
   echo "Enter Admin email ( It can't be empty! )"
   read -e -r -p "Admin email: " admin_email
done 

while [ -z $admin_password ];do
   echo "Enter Admin password (size of password >1) "
   read -s -e -r -p  "Admin password: " admin_password
   echo " "
   read -s -e -r -p  "Confirm admin password: " confirm_admin_password

done 
while [ $admin_password != $confirm_admin_password ]; do
    echo "Entered passwords did not match! Retrying..."
    read -s -e -r -p "Admin password: " admin_password
    echo ""
    read -s -e -r -p "Confirm admin password: " confirm_admin_password
done
echo "Creating admin account: "
python "${root_dir}/install/init_db.py" "${config_db_uri}" "${admin_name}" "${admin_email}" "${admin_password}"
# Create sample database if user wanted to
if [ "${sample_response}" == 'y' ]; then
    echo "Creating sample database.."
    cp -r "${dir}/sample_files/*" "${sample_repository}/TestFiles"
    python "${dir}/sample_db.py" "${config_db_uri}"
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
SAMPLE_REPOSITORY = '${sample_repository}'
SESSION_COOKIE_PATH = '/'
FTP_PORT = $ftp_port
MAX_CONTENT_LENGTH = $max_content_length
MIN_PWD_LEN = $min_pwd_len
MAX_PWD_LEN = $max_pwd_len


# GCP SPECIFIC CONFIG
SCOPES = ['https://www.googleapis.com/auth/cloud-platform']
SERVICE_ACCOUNT_FILE = '${gcp_service_account_file}'
ZONE = '${gcp_instance_zone_name}'
PROJECT_NAME = '${sample_platform_project_name}'
MACHINE_TYPE = f'zones/{ZONE}/machineTypes/${gcp_instance_machine_type}'
WINDOWS_INSTANCE_PROJECT_NAME = '${windows_instance_project_name}'
WINDOWS_INSTANCE_FAMILY_NAME = '${windows_instance_family_name}'
LINUX_INSTANCE_PROJECT_NAME = '${linux_instance_project_name}'
LINUX_INSTANCE_FAMILY_NAME = '${linux_instance_family_name}'
GCP_INSTANCE_MAX_RUNTIME = $gcp_instance_max_runtime  # In minutes
GCS_BUCKET_NAME = '${gcs_bucket_name}'
GCS_SIGNED_URL_EXPIRY_LIMIT = $signed_url_expiry_time  # In minutes
" > "${dir}/../config.py"
# Ensure the files are executable by www-data
chown -R www-data:www-data "${root_dir}" "${sample_repository}"
echo "* Creating startup script"

{
    cp "${dir}/platform" /etc/init.d/platform
    sed -i "s#BASE_DIR#${root_dir}#g" /etc/init.d/platform
    chmod 755 /etc/init.d/platform
    update-rc.d platform defaults
}  >> "$install_log" 2>&1
echo "* Creating RClone config file"

{
    cp  "${root_dir}/install/ci-vm/ci-windows/rclone_sample.conf"  "${root_dir}/install/ci-vm/ci-windows/ci/rclone.conf"
    sed -i "s#GCS_BUCKET_NAME#${gcs_bucket_name}#g" "${root_dir}/install/ci-vm/ci-windows/ci/rclone.conf"
    sed -i "s#GCP_PROJECT_NUMBER#${sample_platform_project_number}#g" "${root_dir}/install/ci-vm/ci-windows/ci/rclone.conf"
    sed -i "s#GCS_BUCKET_LOCATION_TYPE#${gcs_bucket_location_type}#g" "${root_dir}/install/ci-vm/ci-windows/ci/rclone.conf"
    sed -i "s#GCS_BUCKET_LOCATION#${gcs_bucket_location}#g" "${root_dir}/install/ci-vm/ci-windows/ci/rclone.conf"
}  >> "$install_log" 2>&1
echo "* Creating Nginx config"

{
    cp "${dir}/nginx.conf" /etc/nginx/sites-available/platform
    sed -i "s/NGINX_HOST/${config_server_name}/g" /etc/nginx/sites-available/platform
    sed -i "s#SAMPLE_DIR#${sample_repository}/TestFiles/media#g" /etc/nginx/sites-available/platform
    sed -i "s#LOGFILE_DIR#${sample_repository}/LogFiles#g" /etc/nginx/sites-available/platform
    sed -i "s#RESULT_DIR#${sample_repository}/TestResults#g" /etc/nginx/sites-available/platform
    sed -i "s#NGINX_CERT#${config_ssl_cert}#g" /etc/nginx/sites-available/platform 
    sed -i "s#NGINX_KEY#${config_ssl_key}#g" /etc/nginx/sites-available/platform 
    sed -i "s#NGINX_DIR#${root_dir}#g" /etc/nginx/sites-available/platform 
    ln -s /etc/nginx/sites-available/platform /etc/nginx/sites-enabled/platform
} >> "$install_log" 2>&1
echo "* Moving variables and runCI files"

{
    cp $root_dir/install/ci-vm/ci-windows/ci/* "${sample_repository}/TestData/ci-windows/"
    cp $root_dir/install/ci-vm/ci-linux/ci/* "${sample_repository}/TestData/ci-linux/"
} >> "$install_log" 2>&1
echo "* Reloading nginx"
service nginx reload >> "$install_log" 2>&1
echo ""
echo "* Starting Platform..."
service platform start
echo "Platform installed!"
